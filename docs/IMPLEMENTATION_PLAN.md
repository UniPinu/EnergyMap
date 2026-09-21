# IMPLEMENTATION_PLAN.md — Northern European Electricity Balance Terminal

Broad-strokes build plan. Reads against `MVP.md` (the *what* + the math) and `CONTEXT.md` (the *how* of each library/API). Milestones **M1–M5** are the same as `MVP.md §9`; this doc adds architecture, tech choices, build order, and the critical path.

---

## 1. System architecture

Three moving parts. Keep them separate — they have different languages, cadences, and failure modes.

```
┌─────────────────────────┐   one-time / versioned
│  A. Topology preprocessor│  PyPSA-Eur (.nc) ──► topology.json + cluster levels Π₀…Π_L
│     (Python, offline)    │
└────────────┬─────────────┘
             │ static topology (committed artifact)
             ▼
┌─────────────────────────┐   scheduled jobs (respect rate limits)
│  B. Ingestion + API      │  Energinet / ENTSO-E ──► normalize (canonical schema)
│     backend (Python)     │  ──► reconcile balance + residual ──► strain + provenance
│     + time-series store   │  ──► serve cached: /state?level&bbox&t · /series · /zones
└────────────┬─────────────┘
             │ JSON (your own API only)
             ▼
┌─────────────────────────┐
│  C. Frontend (React/TS)  │  shadcn-maps (coarse) ⇆ React Flow (fine) + sidebar charts
│                          │  LOD engine · strain/residual gauges · calendar
└─────────────────────────┘
```

**Why a Python backend is essentially forced:** `pypsa` (topology) and `entsoe-py` (ENTSO-E parsing) are Python. Doing ingestion/analytics in Python and serving via **FastAPI** avoids reimplementing XML parsing and the PyPSA object model in JS. The browser talks only to service B.

---

## 2. Tech decisions (lightweight, with rationale)

| Layer | Choice | Rationale |
|---|---|---|
| Frontend framework | React 19 + **Vite** (or Next if SSR/routing wanted) | shadcn-maps/LIAM target React 19; Vite is enough for an SPA dashboard. |
| Canvas | `@xyflow/react` v12 | Only realistic node-edge lib with the needed control (CONTEXT §1.1). |
| Geographic layer | **shadcn maps** (copy-in) | SVG choropleth + region click for coarse LOD (CONTEXT §1.3). |
| Charts | **shadcn/ui charts** (Recharts) | Sidebar 24h/week/month (CONTEXT §1.4). |
| Styling | Tailwind v4 + CSS variables | Required by copy-in libs; token theme per node type. |
| Backend | **Python + FastAPI** | Co-locates with pypsa/entsoe-py; async, cache-friendly. |
| Ingestion schedule | APScheduler / cron | Per-source cadence, rate-limit aware (CONTEXT §2). |
| Time-series store | **Postgres + TimescaleDB** (or DuckDB/Parquet for a solo MVP) | Canonical `Sample` long table; history powers calendar + baselines. |
| Data validation | valibot/zod (FE) · pydantic (BE) | External feeds change shape. |
| Deploy | FE static host + BE container; DB managed | Standard; nothing exotic. |

Solo/fast path: swap TimescaleDB→DuckDB+Parquet and APScheduler→a cron script; everything else stands.

---

## 3. Repository layout

```
/topology            # A — Python: PyPSA-Eur export scripts → artifacts/topology.{level}.json
/backend             # B — FastAPI app
  /ingest            #     energinet.py, entsoe.py (one module per source)
  /normalize         #     → canonical Node/Edge/Sample (MVP.md §5)
  /analytics         #     balance+residual (§3.4), strain (§3.5), tracing/provenance (§3.6)
  /api               #     routes: /state, /series, /zones, /provenance
  /store             #     DB models, migrations
/frontend            # C — React app
  /canvas            #     GridCanvas (ReactFlow), nodes/, edges/
  /map               #     shadcn-maps components + custom zone map-data
  /sidebar           #     detail panel + shadcn charts + provenance
  /lod               #     level function, cluster selection, render budget
  /lib               #     projection, schema types, api client
/docs                # MVP.md, CONTEXT.md, IMPLEMENTATION_PLAN.md
```

---

## 4. Build order (phased, keyed to MVP.md milestones)

Each phase lists backend / frontend work and an **exit criterion**. Ship each phase runnable.

### Phase 0 — Foundations (do immediately, in parallel with M1)
- **Request the ENTSO-E token now** (~3 working-day lead — CONTEXT §2.2). Blocks M4.
- Stand up repo, Tailwind v4 + shadcn/ui, FastAPI skeleton, DB with the canonical `Sample` schema.
- Write the **projection helper** (lat/lon → screen) shared by map and canvas.
- **Exit:** empty app renders; DB migrations run; token requested.

### Phase 1 — Skeleton topology (M1)
- **A:** run PyPSA-Eur → export DK + neighbours to `topology.json` at ≥2 cluster levels (CONTEXT §2.3). Commit as artifacts.
- **C:** `GridCanvas` renders the 4 typed nodes (emerald/cyan/amber/violet) at projected coords, immovable, with step edges; LIAM-style node components (CONTEXT §1.2). Static data, no live feed.
- **Exit:** Northern-Europe network renders from `topology.json`; pan/zoom smooth; node click selects.

### Phase 2 — DK live data + sidebar (M2)
- **B:** Energinet ingester → normalize DK1/DK2 gen/load/price/exchange into `Sample`; cache; expose `/series` and `/state` (CONTEXT §2.1). **Decide the bus→zone distribution rule** here — every per-node number depends on it (MVP.md §10).
- **C:** node face shows live 3 stats; sidebar opens on click with shadcn 24h/week/month chart (client-side window filter — CONTEXT §1.4).
- **Exit:** DK nodes show live numbers; sidebar charts switch timescale.

### Phase 3 — Balance, residual & LOD (M3)
- **B:** compute net injections + `A·F = n`, the residual `r(t)`, reconciliation (MVP.md §3.4); aggregate state per cluster level.
- **C:** LOD engine — zoom→level function, cluster swap, `hidden`/`onlyRenderVisibleElements`, ≤300–500 node budget (MVP.md §4, CONTEXT §1.1); **residual gauge** in the UI; coarse level = shadcn-maps zone choropleth (CONTEXT §1.5).
- **Exit:** open view = clean zonal summary; zooming reveals buses/plants within budget; residual visible.

### Phase 4 — Neighbours + strain + calendar (M4)
- **B:** ENTSO-E ingester (cached, throttled) for neighbour zones as super-nodes; strain index `S_R(t)` with baselines from accumulated history (MVP.md §3.5); history queries for the calendar.
- **C:** neighbour zone nodes; per-zone **strain meter** gauge/choropleth tint; **calendar** scrub → reload historical state.
- **Exit:** neighbours live at zone granularity; strain colours zones; calendar replays past grid states.

### Phase 5 — Provenance (M5)
- **B:** interconnector-level flow tracing `Θ` + origin price `π_orig` (Bialek, zone granularity — MVP.md §3.6).
- **C:** load sidebar shows the provenance record `{(origin zone, share, price)}`.
- **Exit:** clicking a DK load shows where its power came from and the price paid, across interconnectors.

**Deferred (post-MVP, per MVP.md §9):** per-plant real-time for non-DK; per-internal-line tracing; price = f(strain) model; real basemap tiles; full WLS state estimation.

---

## 5. Request flow (how a node click resolves)

1. User zooms → `levelForZoom` sets LOD level → FE requests `/state?level=ℓ&bbox=…&t=now`.
2. BE returns cached cluster/node states for that level+viewport (already reconciled).
3. User clicks a node → FE requests `/series?entity=…&range=month` (widest) and `/provenance?entity=…`.
4. Sidebar renders stats + shadcn chart (windowed client-side to 24h/week/month) + provenance list.

Everything the browser hits is service B; B is the only thing that ever touches Energinet/ENTSO-E.

---

## 6. Critical path & sequencing risks

- **ENTSO-E token lead time** → request in Phase 0 or M4 slips.
- **Baselines need history** (`D_ref`, strain/price distributions) → start the Energinet ingester as early as Phase 2 and let it accumulate; backfill DK (multi-year available) to cold-start; accept a warm-up window for neighbours.
- **bus→zone distribution rule** is upstream of every non-DK number → decide it in Phase 2, not Phase 4.
- **React Flow performance** is a design constraint, not a late-stage tune → build the LOD engine in Phase 3 before adding neighbour nodes, or the canvas degrades.
- **Zone choropleth geometry** (DK1/DK2 etc.) isn't a stock shadcn map → budget time for custom `map-data` or approximate at country level for v1 (CONTEXT §1.3).

## 7. De-risking order (what to prove first)

1. PyPSA-Eur export actually yields usable coords/edges for the DK region (Phase 1) — validates the whole topology premise.
2. Energinet → canonical `Sample` → live node (Phase 2) — validates the ingestion/schema loop end to end on the easy source.
3. LOD stays within the render budget at neighbour scale (Phase 3) — validates that the abstraction thesis performs.
4. Only then take on ENTSO-E, strain, and provenance (Phases 4–5), which are additive on a proven core.
