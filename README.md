# Northern European Electricity Balance Terminal

A live, spatial **balance sheet for electricity**: a node–edge network over Northern Europe
(DK at bus granularity, neighbours at zone granularity) in which every node declares what it
injects or withdraws, presented through a level-of-detail engine and reconciled against the
nodal balance identity `A·F = n` — with the reconciliation residual shown, never hidden.

Authoritative documents (read in this order):
[docs/MVP.md](docs/MVP.md) (what + the math) · [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) (architecture + phases) ·
[docs/CONTEXT.md](docs/CONTEXT.md) (how each library/API is used).

## Status

| Phase | Milestone | State |
|---|---|---|
| 0 | Foundations — repo, stack, canonical `Sample` schema, projection helper | ✅ built |
| 1 | Skeleton topology (PyPSA-Eur → React Flow) | ⏳ |
| 2 | DK live data + sidebar (Energinet) | ⏳ |
| 3 | Balance, residual & LOD | ⏳ |
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
.venv/Scripts/python -m uvicorn emap.api.app:app --reload
```

- `http://127.0.0.1:8000/health` — status, applied migrations, UTC server time
- `http://127.0.0.1:8000/docs` — OpenAPI UI
- `http://127.0.0.1:8000/api/samples?entity_id=DK1&quantity=price` — canonical rows (empty until Phase 2)

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

### 3. Verify

```bash
cd backend  && .venv/Scripts/python -m pytest           # schema / store / API tests
cd frontend && npm test && npm run typecheck && npm run check:api
```

`check:api` fails if `frontend/src/lib/api-types.d.ts` is out of date with the backend's
OpenAPI document — regenerate with `npm run gen:api` whenever the API changes.

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
topology/             A — PyPSA-Eur export scripts → topology artifacts (Phase 1)
backend/              B — FastAPI app
  emap/schema/        canonical Node / Edge / Sample (pydantic)  ← the boundary
  emap/store/         DuckDB store + migrations/NNNN_*.sql
  emap/ingest/        energinet.py, entsoe.py (Phases 2, 4)
  emap/normalize/     raw → canonical Sample rows
  emap/analytics/     balance + residual, strain, tracing/provenance
  emap/api/           routes
  scripts/            migrate.py, export_openapi.py
frontend/             C — React 19 + Vite + @xyflow/react + shadcn/ui + Tailwind v4
  src/lib/            projection.ts (shared Web-Mercator), api.ts, api-types.d.ts (generated)
  scripts/gen-api.mjs OpenAPI → TypeScript
```

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
