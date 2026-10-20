-- Runtime operational metadata, migration 2. No customer data is embedded here.
CREATE TABLE exports (
    export_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('backup','memory','learned')),
    absolute_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    lineage_json TEXT NOT NULL CHECK(json_valid(lineage_json)),
    state TEXT NOT NULL CHECK(state IN ('available','withdrawn','removed','modified')),
    created_at TEXT NOT NULL,
    expires_at TEXT
) STRICT;

CREATE TABLE deletion_records (
    deletion_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('tombstoned','scrubbed')),
    created_at TEXT NOT NULL,
    completed_at TEXT
) STRICT;

CREATE INDEX snapshots_created ON snapshots(created_at DESC);
CREATE INDEX suppressions_expiry ON suppressions(expires_at);
CREATE INDEX exports_state ON exports(state,expires_at);
