"""Validate the implementation design, not a running companion.

Uses only stdlib. Contract validation covers the exported schema vocabulary
used in these files; it is not a general Draft 2020-12 implementation.
Release development must also use a full schema meta-validator and host tests.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sqlite3
import sys
import tempfile
import tomllib
import uuid
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "design/contracts.schema.json").read_text(encoding="utf-8"))
CHECKS = []
NOW = "2026-10-12T12:00:00Z"


def ensure(condition, label):
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def validate(value, schema, path="$"):
    """Fail closed on supported schema assertions."""
    if "$ref" in schema:
        target = SCHEMA
        for key in schema["$ref"].removeprefix("#/").split("/"):
            target = target[key]
        validate(value, target, path)
    for branch in schema.get("allOf", []):
        validate(value, branch, path)
    for keyword, needed in (("oneOf", 1), ("anyOf", None)):
        if keyword in schema:
            matches = 0
            for branch in schema[keyword]:
                try:
                    validate(value, branch, path)
                    matches += 1
                except ValueError:
                    pass
            if (needed == 1 and matches != 1) or (needed is None and matches == 0):
                raise ValueError(f"{path}: {keyword} failed")
    if "not" in schema:
        try:
            validate(value, schema["not"], path)
        except ValueError:
            pass
        else:
            raise ValueError(f"{path}: forbidden schema")
    if "if" in schema:
        try:
            validate(value, schema["if"], path)
            branch = schema.get("then", {})
        except ValueError:
            branch = schema.get("else", {})
        validate(value, branch, path)
    expected = schema.get("type")
    if expected:
        types = expected if isinstance(expected, list) else [expected]
        matches = {
            "object": isinstance(value, dict), "array": isinstance(value, list),
            "string": isinstance(value, str), "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool), "null": value is None
        }
        if not any(matches[item] for item in types):
            raise ValueError(f"{path}: wrong type")
    if "const" in schema and (value != schema["const"] or
                              isinstance(value, bool) != isinstance(schema["const"], bool)):
        raise ValueError(f"{path}: wrong constant")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: unknown enum")
    if isinstance(value, dict):
        if any(key not in value for key in schema.get("required", [])):
            raise ValueError(f"{path}: missing required field")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise ValueError(f"{path}: unknown fields")
        for key, item in value.items():
            if key in properties:
                validate(item, properties[key], path + "." + key)
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
            raise ValueError(f"{path}: array size")
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            raise ValueError(f"{path}: repeated item")
        if "items" in schema:
            for index, item in enumerate(value):
                validate(item, schema["items"], f"{path}[{index}]")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", float("inf")):
            raise ValueError(f"{path}: string size")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise ValueError(f"{path}: pattern")
        if schema.get("format") == "uuid":
            try:
                if str(uuid.UUID(value)) != value.lower():
                    raise ValueError("noncanonical UUID")
            except ValueError as exc:
                raise ValueError(f"{path}: UUID") from exc
        if schema.get("format") == "date-time":
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value):
                    raise ValueError("not RFC3339")
                if datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
                    raise ValueError("missing timezone")
            except ValueError as exc:
                raise ValueError(f"{path}: timestamp") from exc
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema.get("minimum", -float("inf")) or value > schema.get("maximum", float("inf")):
            raise ValueError(f"{path}: number bounds")


def schema_vocabulary(node):
    allowed = {"$schema", "$id", "$ref", "$defs", "title", "description", "type", "required", "properties",
               "additionalProperties", "items", "oneOf", "anyOf", "allOf", "not", "if", "then", "else",
               "const", "enum", "minimum", "maximum", "minLength", "maxLength", "pattern", "format",
               "minItems", "maxItems", "uniqueItems"}
    if not isinstance(node, dict):
        return
    unknown = set(node) - allowed
    if unknown:
        raise ValueError(f"Unsupported schema vocabulary: {unknown}")
    if "$ref" in node:
        target = SCHEMA
        for key in node["$ref"].removeprefix("#/").split("/"):
            target = target[key]
    if "pattern" in node:
        re.compile(node["pattern"])
    for field in ("properties", "$defs"):
        for child in node.get(field, {}).values():
            schema_vocabulary(child)
    for field in ("items", "not", "if", "then", "else"):
        if field in node:
            schema_vocabulary(node[field])
    for field in ("oneOf", "anyOf", "allOf"):
        for child in node.get(field, []):
            schema_vocabulary(child)


def rejected_contract(value, label):
    try:
        validate(value, SCHEMA)
    except ValueError:
        CHECKS.append(label)
    else:
        raise AssertionError(label)


def insert(conn, table, values):
    columns = ", ".join(values)
    conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({', '.join('?' for _ in values)})",
                 tuple(values.values()))


def rejected_sql(conn, action, label):
    conn.execute("SAVEPOINT rejection_case")
    try:
        action()
    except sqlite3.IntegrityError:
        CHECKS.append(label)
    else:
        raise AssertionError(label)
    finally:
        conn.execute("ROLLBACK TO rejection_case")
        conn.execute("RELEASE rejection_case")


def migrate(conn, path, version):
    sql = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(sql.encode()).hexdigest()
    ensure(not conn.in_transaction, f"migration {version} begins outside transaction")
    try:
        conn.executescript("BEGIN IMMEDIATE;\n" + sql)
        insert(conn, "schema_migrations", {"version": version, "checksum": digest, "applied_at": NOW})
        ensure(conn.in_transaction, f"migration {version} ledger is in DDL transaction")
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise



def main():
    CHECKS.clear()
    schema_vocabulary(SCHEMA)
    ensure(SCHEMA["$schema"].endswith("2020-12/schema"), "declared schema version")
    examples = json.loads((ROOT / "design/examples.json").read_text(encoding="utf-8"))
    check = json.loads((ROOT / "design/checks.example.json").read_text(encoding="utf-8"))
    for item in examples + [check]:
        validate(item, SCHEMA)
        CHECKS.append("valid synthetic " + item["contract"])
    ensure({item["contract"] for item in examples + [check]} ==
           {name.rsplit("/", 1)[-1] for entry in SCHEMA["oneOf"] for name in [entry["$ref"]]},
           "every exported root contract has a valid example")
    bad = copy.deepcopy(examples[0])
    bad["payload"]["command"] = "arbitrary command"
    rejected_contract(bad, "event does not permit arbitrary commands")
    bad = copy.deepcopy(examples[0])
    bad["payload"]["paths"] = ["../outside.py"]
    rejected_contract(bad, "relative path rejects traversal")
    bad = copy.deepcopy(examples[0])
    bad["event_type"] = "session_start"
    bad["payload"] = {}
    rejected_contract(bad, "session registration cannot be empty")
    bad = copy.deepcopy(examples[1])
    bad["outcome"] = "passed"
    bad["completeness"] = "complete"
    rejected_contract(bad, "zero tests cannot be passed")
    bad = copy.deepcopy(examples[2])
    bad["state"] = "resolved"
    rejected_contract(bad, "resolved challenge requires verification")
    bad = copy.deepcopy(check)
    bad["count_semantics"]["required_min_executed"] = 0
    rejected_contract(bad, "test check requires nonzero execution")
    bad = copy.deepcopy(next(item for item in examples if item["contract"] == "improvement"))
    bad["state"] = "active"
    rejected_contract(bad, "contract forbids activating unevaluated unapproved improvement")
    bad = copy.deepcopy(next(item for item in examples if item["contract"] == "capabilities"))
    bad["status"] = "tested"
    rejected_contract(bad, "contract cannot claim unversioned untested host certification")
    bad = copy.deepcopy(next(item for item in examples if item["contract"] == "job_status"))
    bad["result_ref"]["content_contract"] = "lesson"
    rejected_contract(bad, "job result reference must name a check result")
    bad = copy.deepcopy(next(item for item in examples if item["contract"] == "response"))
    bad["status"] = "complete"
    rejected_contract(bad, "incomplete verification cannot become complete response")
    cancelled_response = copy.deepcopy(next(item for item in examples if item["contract"] == "response"))
    cancelled_response["status"] = "cancelled"
    validate(cancelled_response, SCHEMA)
    CHECKS.append("cancellation has a distinct valid response")
    bad = copy.deepcopy(examples[0])
    bad["event_type"] = "check_result"
    bad["request_id"] = "12579465-3de1-4a16-bb40-3fac69bf6e83"
    bad["payload"] = {"result_ref": next(item for item in examples if item["contract"] == "job_status")["result_ref"]}
    rejected_contract(bad, "worker result cannot claim initiating request identity")

    config = tomllib.loads((ROOT / "design/companion.example.toml").read_text(encoding="utf-8"))
    ensure(config["cost"]["max_external_cost_usd"] == 0, "zero required external spend")
    ensure(not config["privacy"]["telemetry"] and not config["privacy"]["remote_upload"], "private local defaults")
    ensure(not config["learning"]["local_training_enabled"], "training remains explicit opt-in")
    ensure(config["memory"]["record_challenges_from"][:2] == ["coding_agent", "companion"], "both actors journaled")
    matrix = json.loads((ROOT / "design/compatibility.json").read_text(encoding="utf-8"))
    ensure(all(item["status"] != "tested" for item in matrix["entries"]), "no untested host presented as tested")

    validation_temp_root = ROOT / ".architecture-validation"
    validation_temp_root.mkdir(exist_ok=True)
    ensure(ROOT in validation_temp_root.resolve().parents, "validation temporary root stays in workspace")
    with tempfile.TemporaryDirectory(prefix="run-", dir=validation_temp_root) as temporary, ExitStack() as resources:
        ensure(validation_temp_root.resolve() in Path(temporary).resolve().parents,
               "computed cleanup target stays in validation directory")
        conn = sqlite3.connect(Path(temporary) / "state.db", autocommit=True)
        resources.callback(conn.close)
        conn.execute("PRAGMA foreign_keys=ON")
        ensure(conn.execute("PRAGMA journal_mode=DELETE").fetchone()[0] == "delete", "rollback journal on real file")
        conn.execute("PRAGMA synchronous=FULL")
        migrate(conn, ROOT / "design/schema.sql", 1)
        ensure(conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 1, "migration ledger persisted")
        insert(conn, "project", {"singleton": 1, "project_id": "p1", "root_identity": "synthetic-root",
                                "display_name": "test", "created_at": NOW, "config_json": "{}"})
        rejected_sql(conn, lambda: insert(conn, "project", {
            "singleton": 2, "project_id": "p2", "root_identity": "other-root", "display_name": "other",
            "created_at": NOW, "config_json": "{}"}), "one project per database")
        session = {"session_id": "s1", "project_id": "p1", "host_name": "synthetic", "capabilities_json": "{}",
                   "policy_hash": "a"*64, "started_at": NOW, "state": "active"}
        insert(conn, "sessions", session)
        rejected_sql(conn, lambda: insert(conn, "sessions", {**session, "session_id": "wrong", "project_id": "unknown"}),
                     "foreign project session rejected")
        for sid in ("snap1", "snap2"):
            insert(conn, "snapshots", {"snapshot_id": sid, "manifest_hash": "a"*64, "environment_hash": "b"*64,
                                      "policy_hash": "c"*64, "created_at": NOW, "coverage_json": "{}", "state": "current"})
        insert(conn, "check_definitions", {"check_id": "test", "version": "1", "manifest_hash": "a"*64,
                                         "manifest_json": "{}", "provenance_json": "{}", "trust_state": "approved"})
        event = {"event_id": "e1", "session_id": "s1", "request_id": "request1", "producer": "synthetic",
                 "event_type": "check_request", "payload_hash": "a"*64, "payload_json": "{}",
                 "created_at": NOW, "received_at": NOW, "state": "queued"}
        insert(conn, "events", event)
        rejected_sql(conn, lambda: insert(conn, "events", event), "duplicate event rejected")
        rejected_sql(conn, lambda: insert(conn, "events", {**event, "event_id": "e2"}), "request ID cannot be reused")
        for result_event_id in ("result-event1", "result-event2"):
            insert(conn, "events", {**event, "event_id": result_event_id, "request_id": None,
                                   "origin_request_id": "request1", "event_type": "check_result"})
        ensure(conn.execute("SELECT count(*) FROM events WHERE origin_request_id='request1'").fetchone()[0] == 2,
               "multiple worker results correlate without reusing request identity")
        rejected_sql(conn, lambda: insert(conn, "events", {**event, "event_id": "e3", "request_id": None,
                                                         "payload_json": "bad JSON"}), "invalid persisted JSON rejected")
        run = {"run_id": "r1", "event_id": "e1", "session_id": "s1", "snapshot_id": "snap1",
               "check_id": "test", "check_version": "1", "outcome": "failed",
               "completeness": "complete", "discovered_count": 1, "executed_count": 1, "skipped_count": 0,
               "result_json": "{}"}
        insert(conn, "runs", run)
        rejected_sql(conn, lambda: insert(conn, "runs", {**run, "run_id": "r2", "outcome": "passed",
                                                      "completeness": "partial"}), "partial verification cannot pass")
        rejected_sql(conn, lambda: insert(conn, "runs", {**run, "run_id": "r3", "outcome": "passed",
                                                      "discovered_count": 0, "executed_count": 0}), "SQL zero-test pass rejected")
        finding = {"finding_id": "f1", "fingerprint": "fp1", "category": "tests", "severity": "high",
                   "confidence": "high", "classification": "confirmed_defect", "rule_id": "test.rule",
                   "rule_version": "1", "lifecycle": "new", "title": "synthetic", "first_seen_at": NOW, "last_seen_at": NOW}
        insert(conn, "findings", finding)
        insert(conn, "findings", {**finding, "finding_id": "f2", "fingerprint": "fp2"})
        observation = {"observation_id": "o1", "finding_id": "f1", "run_id": "r1", "snapshot_id": "snap1",
                       "classification": "confirmed_defect", "rule_id": "test.rule", "rule_version": "1",
                       "severity": "high", "confidence": "high", "location_json": "[]", "expected": "works",
                       "expected_basis": "synthetic invariant", "actual": "failed", "evidence_json": "[]",
                       "reproduction_json": "{}", "remedy_json": "{}", "verification_json": "{}",
                       "created_at": NOW, "freshness": "current"}
        insert(conn, "observations", observation)
        rejected_sql(conn, lambda: insert(conn, "observations", {**observation, "observation_id": "o2",
                                                               "finding_id": "f2", "snapshot_id": "snap2"}),
                     "observation snapshot must match run")
        rejected_sql(conn, lambda: conn.execute("UPDATE observations SET severity='low' WHERE observation_id='o1'"),
                     "observation evidence is immutable")
        delivery = {"session_id": "s1", "finding_id": "f1", "observation_id": "o1", "payload_hash": "a"*64,
                    "status": "pending", "created_at": NOW}
        insert(conn, "deliveries", delivery)
        rejected_sql(conn, lambda: insert(conn, "deliveries", {**delivery, "finding_id": "f2", "payload_hash": "b"*64}),
                     "delivery cannot mismatch finding and observation")
        challenge = {"challenge_id": "ch1", "actor": "companion", "kind": "parser", "stage": "checking",
                     "goal": "read report", "symptoms": "format changed", "constraints_json": "[]",
                     "attempts_json": "[]", "hypotheses_json": "[]", "applicability_json": "[]",
                     "provenance_json": "{}", "evidence_json": "[]", "state": "open", "created_at": NOW,
                     "updated_at": NOW}
        insert(conn, "challenges", challenge)
        rejected_sql(conn, lambda: insert(conn, "challenges", {**challenge, "challenge_id": "ch2", "state": "resolved"}),
                     "resolved journal entry needs verification")
        lesson = {"lesson_id": "l1", "challenge_id": "ch1", "scope": "project", "status": "candidate",
                  "summary": "synthetic parser lesson", "tags": "parser", "applicability_json": "[]",
                  "provenance_json": "{}", "evidence_json": "[]", "privacy_class": "project_private", "created_at": NOW}
        insert(conn, "lessons", lesson)
        rejected_sql(conn, lambda: insert(conn, "lessons", {**lesson, "lesson_id": "l2", "status": "verified"}),
                     "verified lesson needs verification timestamp")
        rejected_sql(conn, lambda: insert(conn, "lessons", {**lesson, "lesson_id": "l3", "scope": "sanitized_shared"}),
                     "private lesson cannot enter shared scope")
        candidate = {"candidate_id": "ic1", "kind": "code", "base_version": "1", "base_package_sha256": "a"*64,
                     "proposed_hash": "b"*64, "evaluator_sha256": "c"*64, "heldout_fixture_sha256": "d"*64,
                     "proposal_json": "{}", "evaluation_json": "{}", "state": "proposed", "approval_json": "{}",
                     "created_at": NOW}
        insert(conn, "improvement_candidates", candidate)
        rejected_sql(conn, lambda: insert(conn, "improvement_candidates", {**candidate, "candidate_id": "ic2",
                            "state": "active", "activated_at": NOW}), "unevaluated improvement cannot activate")
        migrate(conn, ROOT / "design/memory_fts.sql", 2)
        ensure(conn.execute("SELECT count(*) FROM lesson_search").fetchone()[0] == 0, "candidate lessons are not indexed")
        conn.execute("UPDATE lessons SET status='verified', verified_at=? WHERE lesson_id='l1'", (NOW,))
        ensure(conn.execute("SELECT count(*) FROM lesson_search WHERE lesson_search MATCH 'parser'").fetchone()[0] == 1,
               "verified lesson becomes searchable")
        conn.execute("UPDATE lessons SET status='revoked' WHERE lesson_id='l1'")
        ensure(conn.execute("SELECT count(*) FROM lesson_search").fetchone()[0] == 0, "revoked lesson leaves search index")
        ensure(conn.execute("PRAGMA foreign_key_check").fetchall() == [], "foreign-key integrity")
        ensure(conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "database integrity")
        backup = sqlite3.connect(":memory:", autocommit=True)
        resources.callback(backup.close)
        conn.backup(backup)
        ensure(backup.execute("SELECT count(*) FROM challenges").fetchone()[0] == 1, "backup restores challenge history")
        ensure(backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "restored backup integrity")
        backup.close()
        conn.close()
        interrupted = sqlite3.connect(":memory:", autocommit=True)
        resources.callback(interrupted.close)
        interrupted.executescript("BEGIN IMMEDIATE;\n" + (ROOT / "design/schema.sql").read_text(encoding="utf-8"))
        insert(interrupted, "schema_migrations", {"version": 1, "checksum": "synthetic", "applied_at": NOW})
        interrupted.execute("ROLLBACK")
        ensure(interrupted.execute("SELECT count(*) FROM sqlite_master WHERE name='project'").fetchone()[0] == 0,
               "interrupted migration rolls back DDL and ledger together")
        interrupted.close()
    validation_temp_root.rmdir()

    requirements = (ROOT / "COMPANION_REQUIREMENTS.md").read_text(encoding="utf-8")
    plan = (ROOT / "IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")
    ids = re.findall(r"(?m)^- ([A-Z]\d{2}):", requirements)
    plan_ids = re.findall(r"(?m)^\| ([A-Z]\d{2}) \|", plan)
    packs = re.findall(r"(?m)^### (C\d{2}) ", requirements)
    ensure(len(ids) == len(set(ids)), "requirement IDs unique")
    ensure(set(ids) | set(packs) == set(plan_ids), "all requirements and detector packs traced")
    ensure(len(plan_ids) == len(set(plan_ids)), "traceability rows unique")
    summary = {"status": "passed", "checks": len(CHECKS), "requirements": len(ids),
                      "detector_families": len(packs), "schema_contracts": len(SCHEMA["oneOf"]),
                      "sqlite": sqlite3.sqlite_version,
                      "boundary": "design artifacts only; schema subset validator, not runtime/host verification",
                      "passed_checks": CHECKS}
    if "--write-report" in sys.argv:
        (ROOT / "design/validation_report.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "passed_checks"}
                     if "--summary" in sys.argv else summary, indent=2))


if __name__ == "__main__":
    main()
