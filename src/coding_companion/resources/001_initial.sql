-- Architecture schema v1. Not a running companion.
-- Coordinator acquires exclusive ownership before applying this migration.
-- Configure PRAGMAs before starting the transaction. Apply this script with
-- "BEGIN IMMEDIATE;" prefixed in executescript, write the parameterized migration
-- ledger row on that same connection, then COMMIT. On any error ROLLBACK.
-- Do not call executescript inside an existing transaction: its legacy behavior
-- can commit that transaction before executing the script.
-- Runtime must feature-probe SQLite >= 3.38, JSON support, and STRICT tables.
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY CHECK (version > 0),
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
) STRICT;

CREATE TABLE project (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    project_id TEXT NOT NULL UNIQUE,
    root_identity TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    config_json TEXT NOT NULL CHECK (json_valid(config_json))
) STRICT;

CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES project(project_id),
    host_name TEXT NOT NULL,
    host_version TEXT,
    adapter_version TEXT,
    capabilities_json TEXT NOT NULL CHECK (json_valid(capabilities_json)),
    policy_hash TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    state TEXT NOT NULL CHECK (state IN ('active','idle','ended','interrupted'))
) STRICT;

CREATE TABLE snapshots (
    snapshot_id TEXT PRIMARY KEY,
    manifest_hash TEXT NOT NULL,
    environment_hash TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    git_head TEXT,
    created_at TEXT NOT NULL,
    coverage_json TEXT NOT NULL CHECK (json_valid(coverage_json)),
    state TEXT NOT NULL CHECK (state IN ('current','historical','partial'))
) STRICT;

CREATE TABLE snapshot_files (
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL CHECK (length(relative_path) > 0),
    content_hash TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    input_kind TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, relative_path)
) STRICT;

CREATE TABLE check_definitions (
    check_id TEXT NOT NULL,
    version TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    manifest_json TEXT NOT NULL CHECK (json_valid(manifest_json)),
    provenance_json TEXT NOT NULL CHECK (json_valid(provenance_json)),
    trust_state TEXT NOT NULL CHECK (trust_state IN ('unreviewed','approved','revoked')),
    PRIMARY KEY (check_id, version)
) STRICT;

CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(session_id),
    request_id TEXT UNIQUE,
    origin_request_id TEXT REFERENCES events(request_id),
    producer TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    created_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    deadline_at TEXT,
    state TEXT NOT NULL CHECK (state IN ('queued','processing','processed','rejected','expired')),
    result_json TEXT CHECK (result_json IS NULL OR json_valid(result_json))
) STRICT;

CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    event_id TEXT REFERENCES events(event_id),
    session_id TEXT REFERENCES sessions(session_id),
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    check_id TEXT NOT NULL,
    check_version TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    outcome TEXT NOT NULL CHECK (outcome IN
        ('queued','running','passed','failed','execution_error','blocked','skipped',
         'not_applicable','inconclusive','cancelled','superseded')),
    completeness TEXT NOT NULL CHECK (completeness IN ('complete','partial','none')),
    exit_code INTEGER,
    discovered_count INTEGER CHECK (discovered_count IS NULL OR discovered_count >= 0),
    executed_count INTEGER CHECK (executed_count IS NULL OR executed_count >= 0),
    skipped_count INTEGER CHECK (skipped_count IS NULL OR skipped_count >= 0),
    duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
    result_json TEXT NOT NULL CHECK (json_valid(result_json)),
    FOREIGN KEY (check_id, check_version) REFERENCES check_definitions(check_id, version),
    CHECK (outcome != 'passed' OR completeness = 'complete'),
    CHECK (outcome != 'passed' OR discovered_count IS NULL OR discovered_count > 0),
    CHECK (outcome != 'passed' OR executed_count IS NULL OR executed_count > 0),
    CHECK (executed_count IS NULL OR discovered_count IS NULL OR executed_count <= discovered_count),
    CHECK (skipped_count IS NULL OR discovered_count IS NULL OR skipped_count <= discovered_count)
) STRICT;

CREATE TABLE findings (
    finding_id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low','info')),
    confidence TEXT NOT NULL CHECK (confidence IN ('high','medium','low')),
    classification TEXT NOT NULL CHECK (classification IN
        ('confirmed_defect','check_failure','predicted_risk','inconclusive')),
    rule_id TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    lifecycle TEXT NOT NULL CHECK (lifecycle IN
        ('new','acknowledged','investigating','fixing','verified_resolved',
         'dismissed','accepted_risk','reopened','stale')),
    title TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
) STRICT;

CREATE TABLE artifacts (
    artifact_id TEXT PRIMARY KEY,
    relative_state_path TEXT NOT NULL UNIQUE,
    media_type TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    redaction_state TEXT NOT NULL CHECK (redaction_state IN ('sanitized','synthetic')),
    created_at TEXT NOT NULL,
    expires_at TEXT,
    state TEXT NOT NULL CHECK (state IN ('available','expired','missing','quarantined'))
) STRICT;

CREATE TABLE observations (
    observation_id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL REFERENCES findings(finding_id),
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    classification TEXT NOT NULL CHECK (classification IN
        ('confirmed_defect','check_failure','predicted_risk','inconclusive')),
    rule_id TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low','info')),
    confidence TEXT NOT NULL CHECK (confidence IN ('high','medium','low')),
    location_json TEXT NOT NULL CHECK (json_valid(location_json)),
    expected TEXT NOT NULL,
    expected_basis TEXT NOT NULL,
    actual TEXT NOT NULL,
    evidence_json TEXT NOT NULL CHECK (json_valid(evidence_json)),
    reproduction_json TEXT NOT NULL CHECK (json_valid(reproduction_json)),
    remedy_json TEXT NOT NULL CHECK (json_valid(remedy_json)),
    verification_json TEXT NOT NULL CHECK (json_valid(verification_json)),
    created_at TEXT NOT NULL,
    freshness TEXT NOT NULL CHECK (freshness IN ('current','stale','inconclusive')),
    UNIQUE (finding_id, run_id),
    FOREIGN KEY (run_id, snapshot_id) REFERENCES runs(run_id, snapshot_id)
) STRICT;

-- This composite key enforces that observation snapshots belong to their run.
CREATE UNIQUE INDEX runs_identity_snapshot ON runs(run_id, snapshot_id);
CREATE UNIQUE INDEX observations_identity_finding ON observations(observation_id, finding_id);

CREATE TRIGGER observations_evidence_immutable
BEFORE UPDATE OF finding_id, run_id, snapshot_id, classification, rule_id,
    rule_version, severity, confidence, location_json, expected, expected_basis,
    actual, evidence_json, reproduction_json, remedy_json, verification_json,
    created_at ON observations
BEGIN
    SELECT RAISE(ABORT, 'observation evidence is immutable');
END;

CREATE TABLE observation_artifacts (
    observation_id TEXT NOT NULL REFERENCES observations(observation_id) ON DELETE CASCADE,
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    role TEXT NOT NULL,
    PRIMARY KEY (observation_id, artifact_id)
) STRICT;

CREATE TABLE deliveries (
    delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    finding_id TEXT NOT NULL REFERENCES findings(finding_id),
    observation_id TEXT NOT NULL REFERENCES observations(observation_id),
    payload_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','delivered','acknowledged','failed','expired')),
    created_at TEXT NOT NULL,
    delivered_at TEXT,
    acknowledged_at TEXT,
    UNIQUE (session_id, observation_id, payload_hash),
    FOREIGN KEY (observation_id, finding_id) REFERENCES observations(observation_id, finding_id)
) STRICT;

CREATE TABLE suppressions (
    suppression_id TEXT PRIMARY KEY,
    finding_id TEXT REFERENCES findings(finding_id),
    rule_id TEXT,
    scope_json TEXT NOT NULL CHECK (json_valid(scope_json)),
    reason TEXT NOT NULL CHECK (length(reason) > 0),
    created_at TEXT NOT NULL,
    expires_at TEXT,
    CHECK (finding_id IS NOT NULL OR rule_id IS NOT NULL)
) STRICT;

CREATE TABLE challenges (
    challenge_id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(session_id),
    run_id TEXT REFERENCES runs(run_id),
    finding_id TEXT REFERENCES findings(finding_id),
    actor TEXT NOT NULL CHECK (actor IN ('coding_agent','companion','user','external_tool')),
    kind TEXT NOT NULL,
    stage TEXT NOT NULL,
    goal TEXT NOT NULL,
    symptoms TEXT NOT NULL,
    constraints_json TEXT NOT NULL CHECK (json_valid(constraints_json)),
    attempts_json TEXT NOT NULL CHECK (json_valid(attempts_json)),
    hypotheses_json TEXT NOT NULL CHECK (json_valid(hypotheses_json)),
    applicability_json TEXT NOT NULL CHECK (json_valid(applicability_json)),
    provenance_json TEXT NOT NULL CHECK (json_valid(provenance_json)),
    blocker TEXT,
    evidence_json TEXT NOT NULL CHECK (json_valid(evidence_json)),
    state TEXT NOT NULL CHECK (state IN ('open','blocked','resolved','abandoned')),
    resolution TEXT,
    verification_run_id TEXT REFERENCES runs(run_id),
    recurrence_count INTEGER NOT NULL DEFAULT 1 CHECK (recurrence_count > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT,
    CHECK (state != 'resolved' OR (resolution IS NOT NULL AND verification_run_id IS NOT NULL))
) STRICT;

CREATE TABLE lessons (
    lesson_id TEXT PRIMARY KEY,
    challenge_id TEXT REFERENCES challenges(challenge_id) ON DELETE SET NULL,
    scope TEXT NOT NULL CHECK (scope IN ('project','sanitized_shared')),
    status TEXT NOT NULL CHECK (status IN ('candidate','verified','rejected','revoked','expired')),
    summary TEXT NOT NULL,
    tags TEXT NOT NULL,
    applicability_json TEXT NOT NULL CHECK (json_valid(applicability_json)),
    provenance_json TEXT NOT NULL CHECK (json_valid(provenance_json)),
    evidence_json TEXT NOT NULL CHECK (json_valid(evidence_json)),
    privacy_class TEXT NOT NULL CHECK (privacy_class IN ('project_private','sanitized_generic')),
    verified_at TEXT,
    expires_at TEXT,
    created_at TEXT NOT NULL,
    CHECK (status != 'verified' OR verified_at IS NOT NULL),
    CHECK (scope != 'sanitized_shared' OR privacy_class = 'sanitized_generic')
) STRICT;

CREATE TABLE improvement_candidates (
    candidate_id TEXT PRIMARY KEY,
    challenge_id TEXT REFERENCES challenges(challenge_id) ON DELETE SET NULL,
    kind TEXT NOT NULL CHECK (kind IN ('lesson','rule','code','adapter','ranking','trained_component')),
    base_version TEXT NOT NULL,
    base_package_sha256 TEXT NOT NULL,
    proposed_hash TEXT NOT NULL,
    evaluator_sha256 TEXT NOT NULL,
    heldout_fixture_sha256 TEXT NOT NULL,
    proposal_json TEXT NOT NULL CHECK (json_valid(proposal_json)),
    evaluation_json TEXT NOT NULL CHECK (json_valid(evaluation_json)),
    state TEXT NOT NULL CHECK (state IN ('proposed','reproduced','evaluated','approved','active','rejected','rolled_back')),
    evaluation_passed INTEGER NOT NULL DEFAULT 0 CHECK (evaluation_passed IN (0,1)),
    approval_json TEXT NOT NULL CHECK (json_valid(approval_json)),
    created_at TEXT NOT NULL,
    activated_at TEXT,
    CHECK (state NOT IN ('approved','active') OR evaluation_passed = 1),
    CHECK (state != 'active' OR activated_at IS NOT NULL)
) STRICT;

CREATE TABLE learned_artifacts (
    learned_artifact_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES improvement_candidates(candidate_id),
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    version TEXT NOT NULL,
    dataset_lineage_json TEXT NOT NULL CHECK (json_valid(dataset_lineage_json)),
    authorization_json TEXT NOT NULL CHECK (json_valid(authorization_json)),
    evaluation_json TEXT NOT NULL CHECK (json_valid(evaluation_json)),
    state TEXT NOT NULL CHECK (state IN ('candidate','active','disabled','rolled_back','deleted')),
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE audit_entries (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(session_id),
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    details_json TEXT NOT NULL CHECK (json_valid(details_json)),
    created_at TEXT NOT NULL
) STRICT;

CREATE INDEX events_queue ON events(state, received_at);
CREATE INDEX runs_status ON runs(outcome, started_at);
CREATE INDEX findings_active ON findings(lifecycle, severity, last_seen_at);
CREATE INDEX observations_latest ON observations(finding_id, created_at);
CREATE INDEX deliveries_cursor ON deliveries(session_id, delivery_id);
CREATE INDEX challenges_actor_state ON challenges(actor, state, updated_at);
CREATE INDEX lessons_retrieval ON lessons(status, scope, expires_at);

-- Migration checksum/applied record must commit atomically with the DDL.
-- Cross-record lifecycle proofs, timestamp formats, path safety, and test-count
-- semantics beyond these constraints must also be enforced by runtime contracts.
