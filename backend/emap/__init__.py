"""emap — Northern European Electricity Balance Terminal backend (service B).

Sub-packages follow IMPLEMENTATION_PLAN.md §3:
  schema/     canonical Node / Edge / Sample models (MVP.md §5)
  store/      DuckDB store + versioned migrations
  ingest/     one module per external source (energinet, entsoe)
  normalize/  raw payload -> canonical Sample rows
  analytics/  balance + residual (§3.4), strain (§3.5), tracing/provenance (§3.6)
  api/        FastAPI routes — the only thing the browser ever talks to
"""

__version__ = "0.0.1"
