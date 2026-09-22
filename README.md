# Northern European Electricity Balance Terminal

A live, spatial **balance sheet for electricity**: a node–edge network over Northern Europe
(DK at bus granularity, neighbours at zone granularity) in which every node declares what it
injects or withdraws, presented through a level-of-detail engine and reconciled against the
nodal balance identity `A·F = n` — with the reconciliation residual shown, never hidden.

Authoritative documents (read in this order):
[docs/MVP.md](docs/MVP.md) (what + the math) · [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) (architecture + phases) ·
[docs/CONTEXT.md](docs/CONTEXT.md) (how each library/API is used).
How the built system actually works, end to end: [docs/APP_CONTEXT.md](docs/APP_CONTEXT.md).

## Status

| Phase | Milestone | State |
|---|---|---|
| 0 | Foundations — repo, stack, canonical `Sample` schema, projection helper | ✅ built |
| 1 | Skeleton topology (PyPSA-Eur → React Flow) | ✅ built |
| 2 | DK live data + sidebar (Energinet) | ✅ built |
| 3 | Balance, residual & LOD | ✅ built |
| 4 | Neighbours + strain + calendar (ENTSO-E) | ⏳ |
| 5 | Provenance (Bialek tracing) | ⏳ |

## Prerequisites

- **Node ≥ 22** (npm ships with it)
- **Python ≥ 3.12**
- git

No Docker: the time-series store is a single-file **DuckDB** (see *Decisions*).

## Setup (clean clone → running app)

```bash
git clone <repo> EnergyMap && cd EnergyMap
cp .env.example .env            # edit later; secrets live here, never in git
```

### 1. Backend (service B — the only thing the browser talks to)

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"      # Windows
# .venv/bin/pip install -e ".[dev]"        # macOS / Linux
.venv/Scripts/python scripts/migrate.py    # creates backend/data/energymap.duckdb, applies migrations
.venv/Scripts/python -m emap.ingest.backfill --days 35 --weeks 12   # ~3 min: DK history from Energinet
.venv/Scripts/python -m uvicorn emap.api.app:app --reload
```

The backfill is optional but makes the week/month charts meaningful on day 1 (35 days of
5-min production/exchange/CO₂, 12 weeks of hourly load and 15-min prices ≈ 330k rows, 18 MB).
The running API keeps ingesting on its own: `ElectricityProdex5MinRealtime` and `CO2Emis`
every 5 min, `GenerationProdTypeExchange` every 20 min, `DayAheadPrices` hourly — one request
per source update frequency with a dynamic window, never from the browser.

- `http://127.0.0.1:8000/health` — status, applied migrations, UTC server time
- `http://127.0.0.1:8000/docs` — OpenAPI UI
- `http://127.0.0.1:8000/api/samples?entity_id=DK1&quantity=price` — canonical rows (empty until Phase 2)
- `http://127.0.0.1:8000/api/topology` — the static network (validated at startup from
  `topology/artifacts/topology.json`; the app refuses to boot on a broken artifact)
- `http://127.0.0.1:8000/api/state` — per-node state vectors (§3.2), corridor flows, zone
  totals with the raw residual, cluster sums; `?t=` for a past instant (UTC ISO)
- `http://127.0.0.1:8000/api/series?entity_id=DK1&quantity=demand` — canonical or derived series
  (`quantity=residual` / `residual_hat` for the derived closure history)
- `http://127.0.0.1:8000/api/ingest/status` — last run / rows / error per ingestion job

Run **one** uvicorn worker (the default): DuckDB is single-writer and the scheduled ingesters
(Phase 2+) run inside the API process.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (default `http://localhost:5173`). If Vite picks another port, add it
to `EMAP_CORS_ORIGINS` in `.env` and restart the backend. The footer shows the backend status
read from `/health`.

What you see (Phase 3): the open view is the **zonal summary** — a shadcn-maps choropleth of
the bidding zones tinted by the reconciliation residual r̂ (the tint is Π₀-only; the zone
outlines stay as a faint underlay at every zoom), with one super-node card per zone
(DK1/DK2 live, neighbours "—" until Phase 4). **Zoom drives the level** (MVP §4.2): Π₀ zones →
Π₁ k-means bus clusters inside DK → Π₂ every DK bus, plant, load, distributed-generation and
storage node, always within the 400-node render budget (the toolbar shows mounted/budget; the
level buttons zoom to a level's band). Node faces show the three headline statistics of their
kind from the *reconciled* live state (◌ = held value). The app bar carries the **residual
gauge** (r̂ per DK zone); the sidebar shows vitals, the zone's raw measurements, the raw
residual, the reconciled state with its adjustments, and shadcn charts (24h / week / month).
The browser polls only this backend.

### 3. Verify

```bash
cd backend  && .venv/Scripts/python -m pytest           # schema / store / API tests
cd frontend && npm test && npm run typecheck && npm run check:api
```

`check:api` fails if `frontend/src/lib/api-types.d.ts` is out of date with the backend's
OpenAPI document — regenerate with `npm run gen:api` whenever the API changes.

Runtime smoke test (needs backend + frontend running and Google Chrome installed; drives it via
`playwright-core`, no browser download):

```bash
cd frontend && npm run smoke -- http://localhost:5173      # screenshots in frontend/.smoke/
```

It reports mounted nodes/edges per level, verifies the four node types, click-selection with
corridor highlighting, immovability, pan/zoom timing, viewport culling, and that the browser
talks only to our own hosts.

Topology builder tests (only if you rebuild the artifact — see [topology/README.md](topology/README.md)):

```bash
cd topology && .venv/Scripts/python -m pytest
```

## ENTSO-E token (do this on day 1 — ~3 working-day lead time)

The neighbour-zone ingester (Phase 4) needs a Transparency Platform token. A human must
obtain it:

1. Register at <https://transparency.entsoe.eu>.
2. Email `transparency@entsoe.eu`, subject **"RESTful API access"**, body = your account e-mail.
3. After approval (~3 working days): *My Account → Web API Security Token → generate* (shown once).
4. Put it in `.env` as `ENTSOE_TOKEN=…`. It is never read by the browser.

## Repository layout (IMPLEMENTATION_PLAN.md §3)

```
docs/                 MVP.md, CONTEXT.md, IMPLEMENTATION_PLAN.md
topology/             A — PyPSA-Eur export → artifacts/topology.json (committed; see its README)
  emap_topology/      sources (pinned URLs+sha256), io, zones, graph, cluster, build
backend/              B — FastAPI app
  emap/schema/        canonical Node / Edge / Sample (pydantic)  ← the boundary
  emap/store/         DuckDB store + migrations/NNNN_*.sql
  emap/ingest/        energinet.py, entsoe.py (Phases 2, 4)
  emap/normalize/     raw → canonical Sample rows
  emap/analytics/     balance + residual, strain, tracing/provenance
  emap/api/           routes
  scripts/            migrate.py, export_openapi.py
frontend/             C — React 19 + Vite + @xyflow/react + shadcn/ui + Tailwind v4
  src/lib/            projection.ts (shared Web-Mercator), api.ts, api-types.d.ts (generated), topology.ts
  src/canvas/         GridCanvas (React Flow), nodes/ (4 typed + cluster), edges/ (corridor)
  src/store/          ui store (level, selection)
  scripts/            gen-api.mjs (OpenAPI → TypeScript), smoke.mjs (runtime checks)
```

## Bus→zone distribution rule (decided in Phase 2, MVP.md §10)

Energinet publishes DK data per bidding zone; the topology is per bus. Every per-node DK number
is a *disaggregation* of a zonal measurement, balance-preserving by construction:

- **Demand.** Zone gross consumption × `dist_key` of each bus-level load node, where the key is
  0.6·population + 0.4·GDP share of the bus's Voronoi cell (Eurostat NUTS3, GISCO NUTS 2021 —
  PyPSA-Eur's rule). Keys sum to 1 per zone; Bornholm's NUTS3 region maps to the nearest DK2 bus.
- **Generation.** Per 5-min production class (offshore, onshore, solar, thermal ≥ 100 MW,
  thermal < 100 MW): each modelled plant gets P ∝ nameplate, capped at u ≤ 1; whatever the
  modelled plants cannot absorb (rooftop PV, units < 20 MW, plants missing from the plant DB)
  goes to one `dg:` "distributed generation" node per bus, split by the same key.
- **Exchange.** One corridor per (DK zone, neighbour): F_e = −(import-positive exchange);
  the Bornholm–SE4 cable is folded into DK2↔SE4. Internal DK line flows are unknown (no load
  flow in the MVP) and stay unrated on the canvas.
- **Demand lag.** Load is hourly and ~2 h behind production; the state carries the last
  published hour forward, flags it `estimated`, and the residual shows the gap honestly.

## Balance and reconciliation (Phase 3, MVP.md §3.4)

- **Identity.** Per DK zone, gen − load − X must close (KCL at the zone; `analytics/balance.py`
  also carries the general incidence matrix `A` and `A·F − n` for any graph).
- **Residual.** r = Σgen − Σload − X on the raw measurements, r̂ = r / Σload. Shown in the app
  bar gauge and the sidebar, stored as `derived` samples (`residual`, `residual_hat`) for every
  5-min instant at which all inputs exist — never a fabricated 0 when they don't.
- **Reconciliation.** Weighted projection onto the constraint, closed form
  x* = x̃ − W⁻¹a(aᵀx̃)/(aᵀW⁻¹a), with trust weights metered flows 4 (held 1) > 5-min production
  1 (held 0.5) > lagged load 0.5 (held 0.1). The node faces show the reconciled state; the
  sidebar shows each term's adjustment. Full WLS state estimation stays post-MVP.
- **LOD.** ℓ*(z) thresholds 0 / 0.08 / 0.28 with ±12 % hysteresis; render set = level nodes
  intersecting the viewport; demote until ≤ 400 mounted. One 36k-px world for all levels so a
  level switch never moves the viewport. Choropleth = authored bidding-zone map-data
  (`topology/emap_topology/mapdata.py`, entsoe-py polygons + Bornholm) in canvas coordinates.

## Decisions

- **Store = DuckDB single file** (`backend/data/energymap.duckdb`, git-ignored). No Docker on the
  dev machine; analytical SQL (medians/percentiles for baselines) is native. Constraint: one
  writer process. Swapping to Postgres/Timescale later touches only `emap/store/`.
- **UTC everywhere.** `Sample.t_utc` must be timezone-aware and is normalized to UTC by pydantic;
  every DuckDB cursor pins `TimeZone='UTC'`, so values round-trip as aware UTC datetimes.
- **Uniqueness key** `(entity_id, quantity, t_utc, source)` — two providers may report the same
  quantity side by side; the read layer applies a source preference.
- **`Sample.value` is `null` iff `quality == 'missing'`** (JSON has no NaN); all other rows carry a
  finite value.
- **Shared contract** = backend OpenAPI → generated TS types; the frontend has no hand-written
  API shapes.
- **Topology source** = PyPSA-Eur's own pinned inputs (OSM prebuilt network 0.7, powerplantmatching
  0.8.1, entsoe-py zone polygons) processed by `topology/`, with Π₁ from PyPSA's native k-means
  busmap — instead of running the Snakemake workflow (no conda/Docker here). Ids are OSM/ppm ids,
  so the artifact is reproducible and rebuildable.
- **One flow world for all levels** (36k px, ≈1° lon ≈ 1000 px) with per-level card scale, so the
  zoom-driven LOD (Phase 3) switches levels without moving the viewport.
- **Canonical grid Δt = 5 min.** Hourly / 15-min natives are expanded onto the grid at ingest
  (first slot `measured`, the rest `interpolated`, native `resolution` kept). A value is fresh
  only if a sample exists at t itself; older values are held (`estimated`) up to a horizon.
- **Zone series are stored, node series are derived.** Zone/class/corridor samples are canonical
  rows; DK plant / dg / load series are computed on read with the distribution rule, so a node's
  history and its live face always agree.
- **Bulk upsert via temp NDJSON + DuckDB `read_json`** — `executemany` runs one prepared
  statement per row (~5 ms/row); the staged load is ~1000× faster with no extra dependency.
