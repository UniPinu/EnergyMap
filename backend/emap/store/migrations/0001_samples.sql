-- Canonical time-series table (MVP.md §5.2). One long-format shape for every
-- source and every quantity. Join key: (entity_id, quantity, t_utc).
-- `source` is part of the uniqueness key so two providers can report the same
-- quantity side by side (the read layer applies a source preference).
CREATE TABLE IF NOT EXISTS samples (
    entity_id   TEXT        NOT NULL,
    entity_kind TEXT        NOT NULL CHECK (entity_kind IN ('node', 'edge')),
    quantity    TEXT        NOT NULL,
    t_utc       TIMESTAMPTZ NOT NULL,
    value       DOUBLE,                 -- NULL iff quality = 'missing'
    unit        TEXT        NOT NULL,
    source      TEXT        NOT NULL,
    resolution  TEXT        NOT NULL,
    quality     TEXT        NOT NULL CHECK (quality IN ('measured', 'interpolated', 'estimated', 'missing')),
    CHECK ((quality = 'missing') = (value IS NULL)),
    PRIMARY KEY (entity_id, quantity, t_utc, source)
);
