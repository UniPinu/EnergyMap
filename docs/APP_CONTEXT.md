# APP_CONTEXT.md — how the application works today

State of the code after Phases 0–3 (`git log` has 27 commits). This describes what the running
system *actually does*, file by file, so a reader can reason about it without re-deriving it.
The authoritative spec remains [MVP.md](MVP.md); library usage notes are in [CONTEXT.md](CONTEXT.md);
the build order in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

Not live yet (later phases): neighbour-zone data (ENTSO-E, Phase 4), the strain index and the
calendar (Phase 4), flow tracing / price provenance (Phase 5), per-unit storage data (no source).

---

## 1. Three processes, one direction of data

```
topology/  (A, offline, Python)      backend/  (B, FastAPI + DuckDB, Python)        frontend/  (C, React)
PyPSA-Eur inputs ──build──►          topology.json ─load+validate at boot─►         GET /api/topology (once)
artifacts/topology.json              Energinet ─APScheduler jobs─► samples table ─► GET /api/state  (every 60 s)
                                     state compute + reconciliation on request      GET /api/series (per sidebar)
```

* **A** runs only when the topology is rebuilt; its output is committed.
* **B** is the *only* process that talks to external sources. It owns the single DuckDB file
  (`backend/data/energymap.duckdb`, git-ignored) and must run as **one uvicorn worker**.
* **C** talks only to B (`VITE_API_BASE`, default `http://127.0.0.1:8000`).

Settings come from the repo-root `.env` (copied from `.env.example`):
`EMAP_DB_PATH`, `EMAP_HOST/PORT`, `EMAP_CORS_ORIGINS` (plus any `localhost`/`127.0.0.1` origin is
allowed by regex), `EMAP_INGEST_ENABLED` (default true; tests set false), `ENTSOE_TOKEN` (unused
until Phase 4), `VITE_API_BASE`.

---

## 2. Service A — the topology artifact (`topology/`)

`python -m emap_topology.build --fetch` produces `topology/artifacts/topology.json`
(328 nodes, 360 edges) from three pinned inputs, all taken from PyPSA-Eur's own registry:

| Input | Version | Used for |
|---|---|---|
| OSM prebuilt electricity network (`buses/lines/links/converters/transformers.csv`) | 0.7 | grid buses ≥ 220 kV, AC lines, HVDC links, transformers |
| powerplantmatching `powerplants.csv` | 0.8.1 | plants → source/storage nodes; neighbour nameplate aggregates |
| entsoe-py bidding-zone GeoJSONs | V0.6.18 | bus/plant → zone (point-in-polygon), zone anchors, the choropleth |
| `data/osm_bus_names.json` | one Overpass query | names for 29 of the 48 DK buses |
| `data/nuts3_dk.geojson`, `data/nuts3_dk_popgdp.csv` | GISCO NUTS 2021, Eurostat 2023/2024 | the demand key |

### 2.1 Zones (`config.py`)
19 zones: `DK1`, `DK2` (detail = modelled at bus level) and 17 super-node zones `DE_LU`, `NL`,
`GB`, `NO1–NO5`, `SE1–SE4`, `PL`, `FI`, `EE`, `LV`, `LT`. GB has no polygon (hard-coded anchor).

### 2.2 Zone assignment (`zones.py`)
country → candidate zones → containing polygon → nearest polygon within `MAX_SNAP_DEG = 0.75°`
(offshore wind farms) → otherwise not modelled (Faroe Islands). Bornholm is forced to DK2 by a
box override because the entsoe-py DK_2 polygon stops at Zealand.

### 2.3 The finest graph Π₂ (`graph.py`) — node/edge id conventions
| Id | Kind | What |
|---|---|---|
| `bus:<osm id>` | grid | every DK AC bus (48: 38×400 kV, 10×220 kV); DC converter buses are collapsed onto their AC side |
| `load:<osm id>` | consumption | one per DK bus, offset (+0.22° lon, −0.14° lat); carries `dist_key` |
| `dg:<osm id>` | source, fuel `distributed` | one per DK bus; receives the generation the modelled plants cannot absorb; carries `dist_key` |
| `plant:<ppm id>` | source | DK plants ≥ 20 MW not retired before 2026, at their real coordinates, attached to the nearest AC bus of their zone |
| `store:<ppm id>` | storage | DK storage ≥ 1 MW (batteries; `energy_mwh` = E_max) |
| `hub:<zone>` | grid | neighbour zone hub — interconnectors land here |
| `zgen:<zone>`, `zload:<zone>`, `zstore:<zone>` | source / consumption / storage | neighbour aggregates (`dist_key` 1.0) |
| `line:`, `xfmr:`, `link:` | ac_line / hvdc_link | DK-internal branches (rating = `s_nom` / `p_nom`) |
| `conn:`, `feed:`, `dg-conn:`, `zgen-conn:`, `zfeed:`, `zstore-conn:` | ac_line | plant/load/dg/aggregate attachments (`feed:`/`dg-conn:` unrated) |
| `ic:<a>--<b>` | interconnector | bundled corridor between a DK bus and a zone hub, or two hubs; members in `edge_members` |
| `link:relation/5487095-400-DC` | interconnector | the Great Belt (Funen → Zealand), the only DK1↔DK2 grid edge |

Verified invariants (tests): the only DK1↔DK2 grid edge is the Great Belt; DK1 (33 buses) and DK2
(15) AC networks are each one connected component; every satellite hangs off exactly one grid node.

### 2.4 Cluster hierarchy (`cluster.py`)
`node.cluster = {0: zone, 1: "<zone>/c<k>" (DK, PyPSA's k-means busmap: DK1 6, DK2 4) or zone
(neighbours), 2: own id}`. `views["0"]` (19 clusters, 37 bundled edges) and `views["1"]` (27, 46)
precompute the *structure* of coarse levels: members, positions (member-bus centroid; zone anchor
at Π₀), member counts, nameplate sums, bundled edges with `rating = Σ members`.

### 2.5 Demand key (`loadkey.py`)
Per DK zone: Voronoi cell of each bus clipped to the zone polygon; NUTS3 population and GDP
spread over cells by area; `dist_key = 0.6·pop share + 0.4·GDP share`; Σ = 1 per zone. Bornholm's
NUTS3 region goes to the nearest DK2 bus.

### 2.6 Map data (`mapdata.py`)
Writes `frontend/src/components/shadcnmaps/map-data/northern-europe.ts`: one SVG path per zone
(18; GB absent), simplified to ~1 km, in **React Flow world pixels** (see §4.2) so the choropleth
aligns with the nodes. A vitest asserts the Python and TypeScript projections agree.

---

## 3. Service B — backend (`backend/emap/`)

### 3.1 Boot (`api/app.py`, `create_app`)
1. Open (or create) the DuckDB file, apply `store/migrations/NNNN_*.sql` (currently `0001_samples`).
2. Load and validate `topology/artifacts/topology.json` into pydantic models (`topology/model.py`):
   dangling edges, non-partitioning views or missing cluster levels abort the boot.
3. Build the ingestion jobs and start APScheduler (`ingest/scheduler.py`) unless
   `EMAP_INGEST_ENABLED=false`; first runs are staggered 2 s + 3 s·i after boot.

### 3.2 Canonical store (`schema/canonical.py`, `store/`)
One long table `samples(entity_id, entity_kind, quantity, t_utc TIMESTAMPTZ, value, unit,
source, resolution, quality)`, primary key `(entity_id, quantity, t_utc, source)`. Every cursor
pins `TimeZone='UTC'`. Pydantic enforces at the boundary: tz-aware timestamps normalized to UTC,
closed vocabularies (`quantity ∈ p_gen | demand | flow | soc | price | strain | residual |
residual_hat | co2_intensity`, `unit ∈ MW | MWh | EUR/MWh | ratio | tCO2/MWh`, `source ∈ energinet |
entsoe | pypsa | derived`, `resolution ∈ PT5M | PT15M | PT60M`, `quality ∈ measured | interpolated |
estimated | missing`), finite values, and `value IS NULL ⇔ quality = 'missing'`.
`upsert_samples` stages rows through a temp NDJSON file and `read_json` (≈1000× faster than
`executemany`); last write wins within a batch.

### 3.3 Ingestion (`ingest/energinet.py`, `ingest/jobs.py`)
Energinet Energi Data Service, no auth, `limit=0`, `start`/`end` in Danish local time (dynamic
`now-…` strings pass through), HTTP 429 honoured via `Retry-After`, every record validated into
a typed row model. Jobs and their windows:

| Job | Dataset | Every | Window | Rows written per run |
|---|---|---|---|---|
| `energinet.prodex` | `ElectricityProdex5MinRealtime` (5-min classes + exchange per neighbour) | 5 min | `now-PT30M` | ~100 |
| `energinet.co2` | `CO2Emis` (5-min g/kWh) | 5 min | `now-PT30M` | ~10 |
| `energinet.genprodtype` | `GenerationProdTypeExchange` (hourly `GrossCon`; ~2 h lag, values revised) | 20 min | `now-PT6H` | ~120 |
| `energinet.dayahead` | `DayAheadPrices` (15-min, DK1/DK2 kept) | 60 min | `now-P1D` … `now+P2D` | ~1200 |
| `derived.residual` | r(t), r̂(t) per DK zone (see §3.6) | 5 min | last 6 h | varies |

`/api/ingest/status` reports last start/ok, rows and error per job.
`python -m emap.ingest.backfill --days 35 --weeks 12` loads history once (~3 min);
`python -m emap.analytics.derive --days 36` backfills the residual series (< 1 s).

### 3.4 Normalization (`normalize/energinet.py`, `normalize/grid.py`)
Canonical grid Δt = **5 min**. Coarser natives are expanded onto it: the first slot keeps
`measured`, the remaining slots are `interpolated`, `resolution` records the native step.
Entity conventions:

| entity_id | quantity | source row |
|---|---|---|
| `DK1` / `DK2` | `demand` (GrossCon, PT60M) · `price` (EUR, PT15M) · `co2_intensity` (g/kWh ÷ 1000 → tCO2/MWh) · `p_gen` (Σ classes) | zone |
| `DK1|wind_offshore`, `…|wind_onshore`, `…|solar`, `…|thermal_ge100`, `…|thermal_lt100` | `p_gen` | Energinet columns OffshoreWindPower, OnshoreWindPower, SolarPower, ProductionGe100MW, ProductionLt100MW |
| corridor edge id (entity_kind `edge`) | `flow` | exchange columns; Energinet is **import-positive**, corridors are oriented DK bus → hub (Funen → Zealand for the Great Belt), so `F_e = −exchange`; DK2's `BornholmSE4` is folded into the DK2↔SE4 corridor |

The (zone, neighbour) → corridor map is derived from the topology (`corridor_map`): DK1 ↔ DE_LU,
NL, GB, NO2, SE3, DK2; DK2 ↔ DE_LU, SE4.

### 3.5 State compute (`analytics/state.py`) — `GET /api/state?t=`
Default `t` = the latest 5-min instant with DK production data; otherwise the requested instant
floored to the grid. For each DK zone:

1. **Read** the latest sample at or before `t` for every quantity (`latest()`): a sample *at* `t`
   keeps its stored quality; anything older is `estimated` (held); beyond a horizon
   (p_gen/flow/co2 60 min, demand 6 h, price 26 h) it is `missing` and returns `None`.
2. **Reconcile** the zone identity gen − load − X = 0 (`analytics/reconcile_zone.py` →
   `analytics/balance.py`): measurements are the five classes (coef +1), demand (−1) and each
   corridor flow (−1 if it leaves the zone, +1 if it enters), with trust weights
   `flow 4 / 1`, `p_gen 1 / 0.5`, `demand 0.5 / 0.1` (measured / held). Closed form
   `x* = x̃ − W⁻¹a(aᵀx̃)/(aᵀW⁻¹a)`. Skipped (`reconciled = null`) when a class total, the load or
   any corridor flow is missing.
3. **Distribute** the *reconciled* class totals and demand onto nodes (`analytics/distribution.py`):
   plant `P = min(cap, P_c · cap/Σcap_c)` per class; remainder `Σ_c max(0, P_c − Σcap_c)` to the
   `dg:` nodes by key; load `D = D_z · key`. Keys are renormalized so sums are exact.
4. **δ(1h)** = the same computation at `t − 1 h`, compared like for like.
5. **Grid buses**: `net_injection` = Σ attached gen − Σ attached load, `net_sign`, `t_flow` =
   ½Σ|F| over *known* incident corridors only (internal DK line flows are unknown: no load flow).
6. **Zone totals**: raw `p_gen`, `demand` (+ `demand_quality`, `demand_age_min`), `exchange` (net
   export), `price`, `co2_intensity`, raw `residual = gen − load − X`, `residual_hat = r / load`,
   plus `reconciled {p_gen, by_class, demand, exchange, flows, adjustments, weights}`.
7. **Clusters** (`views` levels 0 and 1): balance-preserving sums of member node states.

Neighbour zones return `live: false` and their nodes have no state entry (never zeros).

### 3.6 Derived residual series (`analytics/derive.py`)
Set-based SQL per zone: for every grid instant where the zone `p_gen`, `demand` and **all** its
corridor flows exist, write `residual` (MW) and `residual_hat` (ratio) with `source = derived`;
quality `measured` only if every input was measured. No row where the identity cannot be formed.

### 3.7 Series (`analytics/series.py`) — `GET /api/series?entity_id=&quantity=&start=&end=`
Stored entities (zones, classes, corridors, residuals) return their rows. DK plant / dg / load
nodes are **derived on read** with the same distribution rule (`derived_from` says how), so a
node's history matches its face. Default window = last 31 days; points are `{t, v, q}`.

### 3.8 Other endpoints
`/health` (migrations, UTC time), `/api/topology` (the validated artifact, ~165 kB),
`/api/samples` (raw canonical rows for one entity/quantity), `/docs` (OpenAPI UI).
The OpenAPI document is the shared contract: `frontend/npm run gen:api` regenerates
`src/lib/api-types.d.ts`; `check:api` fails when it is stale.

---

## 4. Service C — frontend (`frontend/src/`)

### 4.1 Boot and data loading
`App.tsx` fetches `/health` once, `/api/topology` once (`lib/topology.ts: useTopology`), and
polls `/api/state` every 60 s (`store/live.ts: startStatePolling`). Series are fetched lazily
per `(entity, quantity)` for the widest window (31 days) and cached in the `live` store; the
sidebar windows them client-side. All fetches go through the typed `openapi-fetch` client in
`lib/api.ts`.

### 4.2 One world, one projection (`lib/projection.ts`, `lib/topology.ts`)
`fitBounds({west 3, south 49, east 31, north 71}, 36000×36000 px, padding 600)` — Web-Mercator,
≈ 1° lon ≈ 1000 px. Node `position` = projection of `(lat, lon)` minus half the card
(172 × 132 px at scale 1). This single projection is shared by the canvas and the map-data
(§2.6). Nodes are immovable (`nodesDraggable={false}`, `draggable: false`).

`buildFlow(topology, level)` produces the React Flow arrays for one level: typed entity nodes
at Π₂, `cluster` nodes at Π₀/Π₁ (with per-level card scale via CSS `zoom`: 14 / 4 / 1), and
`corridor` edges whose handle sides are chosen from the relative geometry of the endpoints.
All three levels are built once (`useMemo`) and `applyState` overlays the live snapshot
(nodes without any state keep their identity so memoized components skip them).

### 4.3 LOD engine (`lod/`)
`LodController` (inside `<ReactFlow>`) runs on every viewport change:
* `ℓ*(z) = max{ℓ : z ≥ z_ℓ}` with `LEVEL_ZOOM = [0, 0.08, 0.28]` and a ±12 % hysteresis band;
* counts the level's nodes whose bbox intersects the viewport (what `onlyRenderVisibleElements`
  will mount);
* demotes the level while that count exceeds `N_MAX = 400`;
* publishes `{level, visible, demoted, zoom}` to the UI store; `GridCanvas` swaps the arrays.
The whole Π₂ set is 328 nodes, so demotion is currently exercised only by unit tests.
`lod/selection.ts` remaps the selection across levels (bus → cluster → zone; neighbour zone ↔ hub;
a DK cluster is dropped when descending).

### 4.4 Canvas (`canvas/`)
React Flow in LIAM's configuration: `colorMode="dark"`, dotted background (`#393b3c`, gap 16),
`panOnScroll`, `deleteKeyCode={null}`, `minZoom 0.015`, `maxZoom 6`, `nodeTypes`/`edgeTypes`
hoisted. Highlight semantics are LIAM's `highlightNodesAndEdges`: the selected node is *active*
(2 px accent border); the hovered node, neighbours of the active/hovered node and their
corridors are *highlighted* (1 px accent + glow, edges turn `#1ded83` and carry six travelling
particles). Nothing is dimmed.

Node faces (`canvas/nodes/`): source `P_gen · u · δ 1h`, grid `T · λ · sgn n`, consumption
`D · ρ · δ 1h`, storage `P · SoC · dur`, cluster `n · gen/load · members`. `—` means unknown;
`◌` marks a held value. Edges (`canvas/edges/`): step path, screen-space stroke
(`vector-effect: non-scaling-stroke`), width grows with |F| when measured, tint by loading
(warning ≥ 60 %, danger ≥ 90 %), dashed for HVDC / interconnectors.

`canvas/Toolbar.tsx` (bottom centre): zoom −/%/+, fit view, level buttons that *zoom to* a
level's band centred on Denmark, and the `mounted/400` readout.

### 4.5 Geographic layer (`map/`)
`ZoneChoropleth` renders the shadcn-maps `Map` on the authored map-data inside React Flow's
`ViewportPortal` (world coordinates, `z-index: -1`, non-scaling strokes). At Π₀ regions are
tinted by |r̂| buckets (≤ 2 / 5 / 10 / 20 / > 20 % of load; neighbours neutral) and a region
click selects the zone; at Π₁/Π₂ the tint is dropped and the outlines remain as a faint
underlay. `ResidualGauge` in the app bar shows r̂ per DK zone (`—` when the identity cannot be
formed).

### 4.6 Sidebar (`sidebar/`)
LIAM `TableDetail` drawer (300 px): Head (name, kind, zone), collapsible sections **Vitals**
(the node's state vector + static facts), **Zone balance** (raw measurements incl. held-load
age, raw residual, price, CO₂; reconciled `n*` with Δ per term, closure and trust weights),
**Charts** (range 24h / week / month; the node's own `p_gen` or `demand` series when it has one,
plus the zone's consumption and day-ahead price). Charts are the shadcn `chart` copy-in
(Recharts) with deterministic time ticks; `windowing.ts` slices the cached series to the range
and bucket-averages to ≤ 360 points.

### 4.7 Styling
`styles/liam.css` holds LIAM's tokens verbatim (bg `#141616`, panes `#232526`, accent
`#1ded83`, overlay/pane/node variables, Inter + IBM Plex Mono, 10–14 px scale); `index.css`
maps the shadcn/Tailwind tokens onto them. Node-type colours (MVP §8): source = LIAM's accent,
grid cyan, consumption amber, storage violet. Component CSS files are 1:1 ports of LIAM's
modules (`node.css`, `edge.css`, `toolbar.css`, `detail.css`, `app.css`).

---

## 5. What happens when …

* **the app opens** → fitView on the world (zoom ≈ 0.03) → Π₀: 19 zone cards over the tinted
  choropleth; DK1/DK2 show live `n`, gen/load; neighbours `—`.
* **you zoom in** → at z ≥ 0.08 (+12 %) Π₁: DK k-means clusters + neighbour hubs, outlines only;
  at z ≥ 0.28 Π₂: every DK entity in view (≤ 400 mounted), cards readable from ~40 %.
* **a job fires** → new canonical rows are upserted; the next `/api/state` poll (≤ 60 s) shows
  them; the residual job re-derives the last 6 h.
* **you click a node / region** → selection in the UI store → corridor highlight, sidebar opens,
  series fetched once and windowed locally.
* **the level changes** → selection remapped, arrays swapped, viewport untouched.

## 6. Known limitations (by design or pending)
* Load lags production by ~2 h (source cadence); the state carries it forward as `estimated`
  and the residual shows the gap — that is the intended honesty signal.
* powerplantmatching under-reports DK offshore nameplate (1.6 GW vs > 2 GW observed): modelled
  farms sit at u = 1 and the rest lands on the `dg:` nodes.
* Internal DK line flows are unknown (no load flow); only corridor flows are measured.
* No storage feed exists in the sources; storage faces stay `—`.
* GB has no zone polygon; Bornholm attaches to the nearest Zealand bus.

## 7. Commands
```
backend:   .venv/Scripts/python -m uvicorn emap.api.app:app --reload      (port 8000)
           .venv/Scripts/python scripts/migrate.py
           .venv/Scripts/python -m emap.ingest.backfill --days 35 --weeks 12
           .venv/Scripts/python -m emap.analytics.derive --days 36
           .venv/Scripts/python -m pytest                                   (57 tests)
frontend:  npm run dev -- --port 5174 ; npm test (36) ; npm run typecheck ; npm run check:api
           npm run smoke -- http://localhost:5174                           (35 live checks)
topology:  .venv/Scripts/python -m emap_topology.build --fetch ; -m emap_topology.mapdata ; pytest (24)
```
