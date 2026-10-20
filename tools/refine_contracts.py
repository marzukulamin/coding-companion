"""Maintain architecture contracts/examples and generate requirement traceability.

This is design tooling, not the companion runtime. It performs local file edits.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def obj(properties, required):
    return {"type": "object", "additionalProperties": False,
            "required": required, "properties": properties}


def text(maximum=4000):
    return {"type": "string", "minLength": 1, "maxLength": maximum}


def ref(name):
    return {"$ref": "#/$defs/" + name}


def arr(item, maximum=100, minimum=0):
    return {"type": "array", "minItems": minimum, "maxItems": maximum, "items": item}


def when(field, value, then):
    return {"if": {"properties": {field: {"const": value}}, "required": [field]}, "then": then}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


schema_path = ROOT / "design/contracts.schema.json"
schema = json.loads(schema_path.read_text(encoding="utf-8"))
d = schema["$defs"]
d["blob_ref"] = obj({
    "root": {"const": "request_bodies"}, "path": ref("path"), "sha256": ref("hash"),
    "size_bytes": {"type": "integer", "minimum": 1, "maximum": 1048576},
    "content_contract": {"enum": ["check_result", "challenge", "feedback", "lesson", "improvement", "capabilities"]}
}, ["root", "path", "sha256", "size_bytes", "content_contract"])
d["provenance"] = obj({
    "actor": {"enum": ["coding_agent", "companion", "user", "external_tool"]},
    "source_ids": arr(ref("id")),
    "recorded_at": ref("time"),
    "environment_hash": ref("hash"),
    "ownership": text(1000),
    "privacy_class": {"enum": ["project_private", "sanitized_generic"]}
}, ["actor", "source_ids", "recorded_at", "privacy_class"])
d["session_registration"] = obj({
    "host": text(128), "host_version": {"type": ["string", "null"], "maxLength": 128},
    "adapter_version": text(64), "policy_hash": ref("hash"),
    "capability_mode": {"enum": ["manual", "checkpoint", "live_documented", "live_tested"]}
}, ["host", "host_version", "adapter_version", "policy_hash", "capability_mode"])
d["query"] = obj({
    "kind": {"enum": ["status", "findings", "memory", "capabilities", "challenges"]},
    "cursor": text(256), "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    "text": text(1000), "actor": {"enum": ["all", "coding_agent", "companion", "user", "external_tool"]},
    "include_stale": {"type": "boolean"}
}, ["kind"])
payload = d["event"]["properties"]["payload"]
d["event"]["properties"]["origin_request_id"] = {"type": "string", "format": "uuid"}
payload["properties"].pop("body_ref", None)
payload["properties"].pop("query_kind", None)
payload["properties"].update({
    "session": ref("session_registration"), "result_ref": ref("blob_ref"),
    "challenge_ref": ref("blob_ref"), "feedback_ref": ref("blob_ref"),
    "query": ref("query"), "reason": text(1000),
    "tool_status": obj({"tool_call_id": ref("id"), "exit_code": {"type": ["integer", "null"]}},
                       ["tool_call_id", "exit_code"])
})
event_rules = []
for event_type, keys in {
    "session_start": ["session"], "file_change": ["paths"], "tool_complete": ["tool_status"],
    "check_result": ["result_ref"], "feedback": ["feedback_ref"], "challenge": ["challenge_ref"],
    "query": ["query"], "session_end": ["reason"]
}.items():
    properties = {"payload": {"required": keys}}
    if event_type in ("session_start", "session_end"):
        properties["session_id"] = ref("id")
    if event_type == "file_change":
        properties["payload"]["properties"] = {"paths": {"minItems": 1}}
    body = {"properties": properties}
    if event_type in ("query",):
        body["required"] = ["request_id"]
    event_rules.append(when("event_type", event_type, body))
event_rules.append(when("event_type", "check_request", {
    "required": ["request_id"],
    "properties": {"payload": {"anyOf": [
        {"required": ["profile"]},
        {"required": ["check_ids"], "properties": {"check_ids": {"minItems": 1}}}
    ]}}
}))
for field, contract in [("result_ref", "check_result"), ("challenge_ref", "challenge"), ("feedback_ref", "feedback")]:
    payload["properties"][field] = {"allOf": [ref("blob_ref"), {"properties": {"content_contract": {"const": contract}}}]}
d["event"]["allOf"] = event_rules
d["event"]["allOf"].append(when("event_type", "check_result", {"not": {"required": ["request_id"]}}))
d["check_result"]["allOf"] = [
    when("outcome", "passed", {"properties": {"completeness": {"const": "complete"}}}),
    {"if": {"required": ["counts"], "properties": {"counts": {
        "required": ["discovered"], "properties": {"discovered": {"const": 0}}
    }}}, "then": {"properties": {"outcome": {"not": {"const": "passed"}}}}}
]
cp = d["challenge"]["properties"]
cp.update({
    "session_id": ref("id"), "run_id": ref("id"), "finding_id": ref("id"),
    "constraints": arr(text(1000)), "blocker": text(2000),
    "hypotheses": arr(obj({"statement": text(2000), "confidence": {"enum": ["high", "medium", "low"]}},
                         ["statement", "confidence"])),
    "applicability": arr(text(1000)), "provenance": ref("provenance"),
    "updated_at": ref("time"), "expires_at": ref("time"),
    "recurrence_count": {"type": "integer", "minimum": 1}
})
attempt = cp["attempts"]["items"]
attempt["properties"].update({"evidence": arr(ref("id")), "recorded_at": ref("time"),
                              "provenance": ref("provenance"),
                              "duration_ms": {"type": "integer", "minimum": 0}})
attempt["required"] = ["action", "result", "outcome", "evidence", "recorded_at", "provenance"]
d["challenge"]["required"] += [key for key in ["constraints", "hypotheses", "applicability", "provenance", "updated_at"]
                             if key not in d["challenge"]["required"]]
d["feedback"] = obj({
    "contract": {"const": "feedback"}, "schema_version": {"const": "1.0"},
    "finding_id": ref("id"), "outcome": {"enum": ["resolved", "dismissed", "accepted_risk", "reopened", "diagnosis_wrong"]},
    "reason": text(), "verification_run_id": ref("id"),
    "provenance": ref("provenance")
}, ["contract", "schema_version", "finding_id", "outcome", "reason", "provenance"])
d["feedback"]["allOf"] = [when("outcome", "resolved", {"required": ["verification_run_id"]})]
d["lesson"] = obj({
    "contract": {"const": "lesson"}, "schema_version": {"const": "1.0"},
    "lesson_id": ref("id"), "challenge_id": ref("id"),
    "scope": {"enum": ["project", "sanitized_shared"]},
    "status": {"enum": ["candidate", "verified", "rejected", "revoked", "expired"]},
    "summary": text(), "tags": arr(text(128)), "applicability": arr(text(1000)),
    "evidence": arr(ref("id")), "provenance": ref("provenance"),
    "verified_at": ref("time"), "expires_at": ref("time")
}, ["contract", "schema_version", "lesson_id", "scope", "status", "summary", "tags", "applicability", "evidence", "provenance"])
d["lesson"]["allOf"] = [
    when("status", "verified", {"required": ["verified_at"], "properties": {"evidence": {"minItems": 1}}}),
    when("scope", "sanitized_shared", {"properties": {"provenance": {"properties": {"privacy_class": {"const": "sanitized_generic"}}}}})
]
d["improvement"] = obj({
    "contract": {"const": "improvement"}, "schema_version": {"const": "1.0"},
    "candidate_id": ref("id"), "challenge_id": ref("id"),
    "kind": {"enum": ["lesson", "rule", "code", "adapter", "ranking", "trained_component"]},
    "base_version": text(64), "base_package_sha256": ref("hash"), "proposed_sha256": ref("hash"),
    "evaluator_sha256": ref("hash"), "heldout_fixture_sha256": ref("hash"),
    "state": {"enum": ["proposed", "reproduced", "evaluated", "approved", "active", "rejected", "rolled_back"]},
    "evaluation_passed": {"type": "boolean"},
    "approval": obj({"actor": text(128), "policy_hash": ref("hash"), "approved_at": ref("time")},
                    ["actor", "policy_hash", "approved_at"]),
    "dataset_lineage": arr(text(1000), minimum=1),
    "created_at": ref("time")
}, ["contract", "schema_version", "candidate_id", "kind", "base_version", "base_package_sha256",
    "proposed_sha256", "evaluator_sha256", "heldout_fixture_sha256", "state", "evaluation_passed", "created_at"])
d["improvement"]["allOf"] = [
    when("state", state, {"required": ["approval"], "properties": {"evaluation_passed": {"const": True}}})
    for state in ("approved", "active")
] + [when("kind", "trained_component", {"required": ["dataset_lineage"]})]
d["capabilities"] = obj({
    "contract": {"const": "capabilities"}, "schema_version": {"const": "1.0"},
    "host": text(128), "host_version": {"type": ["string", "null"]},
    "status": {"enum": ["documented_not_tested", "tested", "experimental", "unsupported"]},
    "delivery": {"enum": ["manual", "checkpoint", "safe_point", "host_dependent", "unsupported"]},
    "available_check_ids": arr(ref("id")), "blocked_check_ids": arr(ref("id")),
    "enforced_limits": arr(text(128)), "best_effort_limits": arr(text(128)),
    "tested_at": ref("time")
}, ["contract", "schema_version", "host", "host_version", "status", "delivery", "available_check_ids",
    "blocked_check_ids", "enforced_limits", "best_effort_limits"])
d["capabilities"]["allOf"] = [when("status", "tested", {"required": ["tested_at"],
                                                        "properties": {"host_version": text(128)}})]
d["response"] = obj({
    "contract": {"const": "response"}, "schema_version": {"const": "1.0"},
    "request_id": {"type": "string", "format": "uuid"}, "project_id": ref("id"),
    "status": {"enum": ["accepted", "running", "complete", "incomplete", "blocked", "rejected", "error", "cancelled", "expired"]},
    "run_ids": arr(ref("id")), "finding_ids": arr(ref("id")), "next_cursor": text(256),
    "completeness": {"enum": ["complete", "partial", "none"]},
    "result_ref": ref("blob_ref"),
    "reasons": arr(text(2000)),
    "created_at": ref("time")
}, ["contract", "schema_version", "request_id", "project_id", "status", "run_ids", "finding_ids",
    "completeness", "reasons", "created_at"])
d["response"]["allOf"] = [
    when("status", "complete", {"properties": {"completeness": {"const": "complete"}}})
] + [when("status", status, {"properties": {
    "completeness": {"enum": ["partial", "none"]}, "reasons": {"minItems": 1}
}}) for status in ("incomplete", "blocked", "rejected", "error", "cancelled", "expired")]
d["job_status"] = obj({
    "contract": {"const": "job_status"}, "schema_version": {"const": "1.0"},
    "run_id": ref("id"), "snapshot_id": ref("id"), "check_id": ref("id"),
    "state": {"enum": ["queued", "running", "finished", "cancelled", "superseded"]},
    "completeness": {"enum": ["complete", "partial", "none"]},
    "created_at": ref("time"), "result_ref": {"allOf": [
        ref("blob_ref"), {"properties": {"content_contract": {"const": "check_result"}}}
    ]}
}, ["contract", "schema_version", "run_id", "snapshot_id", "check_id", "state", "completeness", "created_at"])
d["job_status"]["allOf"] = [when("state", "finished", {"required": ["result_ref"]})]
mp = d["check_manifest"]["properties"]
mp.update({
    "applicability": obj({"languages": arr(text(128)), "frameworks": arr(text(128)),
                          "runtime_versions": arr(text(128))},
                         ["languages", "frameworks", "runtime_versions"]),
    "permission_scope": arr(text(128), minimum=1),
    "resources": obj({"max_output_bytes": {"type": "integer", "minimum": 1},
                      "max_artifact_bytes": {"type": "integer", "minimum": 1},
                      "max_memory_mib": {"type": ["integer", "null"], "minimum": 1},
                      "limit_enforcement": {"enum": ["required", "capability_reported"]}},
                     ["max_output_bytes", "max_artifact_bytes", "max_memory_mib", "limit_enforcement"]),
    "verification_check_ids": arr(ref("id"), minimum=1),
    "count_semantics": obj({"kind": {"enum": ["tests", "not_tests"]},
                            "required_min_executed": {"type": "integer", "minimum": 0}},
                           ["kind", "required_min_executed"])
})
for key in ("applicability", "permission_scope", "resources", "verification_check_ids", "count_semantics"):
    if key not in d["check_manifest"]["required"]:
        d["check_manifest"]["required"].append(key)
d["check_manifest"]["allOf"] = [{
    "if": {"properties": {"count_semantics": {"properties": {"kind": {"const": "tests"}}, "required": ["kind"]}}},
    "then": {"properties": {"count_semantics": {"properties": {"required_min_executed": {"minimum": 1}}}}}
}]
root_contracts = ["event", "check_result", "finding", "challenge", "check_manifest",
                  "feedback", "lesson", "improvement", "capabilities", "response", "job_status"]
schema["oneOf"] = [ref(name) for name in root_contracts]
write_json(schema_path, schema)

check_path = ROOT / "design/checks.example.json"
check = json.loads(check_path.read_text(encoding="utf-8"))
check.update({
    "applicability": {"languages": ["python"], "frameworks": ["pytest"], "runtime_versions": ["3.12+"]},
    "permission_scope": ["approved_snapshot_root", "private_artifact_dir"],
    "resources": {"max_output_bytes": 2097152, "max_artifact_bytes": 10485760,
                  "max_memory_mib": 512, "limit_enforcement": "capability_reported"},
    "verification_check_ids": ["python.pytest"],
    "count_semantics": {"kind": "tests", "required_min_executed": 1}
})
write_json(check_path, check)
examples_path = ROOT / "design/examples.json"
examples = json.loads(examples_path.read_text(encoding="utf-8"))
provenance = {"actor": "companion", "source_ids": ["artifact-synthetic-report"],
              "recorded_at": "2026-10-12T12:00:00Z", "privacy_class": "project_private"}
challenge = next(item for item in examples if item["contract"] == "challenge")
challenge.update({"constraints": ["Synthetic offline fixture."], "hypotheses": [],
                  "applicability": ["parser-version-example"], "provenance": provenance,
                  "updated_at": "2026-10-12T12:00:00Z"})
for attempt_value in challenge["attempts"]:
    attempt_value.update({"evidence": ["artifact-synthetic-report"],
                          "recorded_at": "2026-10-12T12:00:00Z", "provenance": provenance})
write_json(examples_path, examples)

# One synthetic valid example for every exported root contract.
finding_example = {
    "contract": "finding", "schema_version": "1.0", "finding_id": "finding-example",
    "rule_id": "browser.hit_test", "rule_version": "0.1.0", "run_id": "run-browser",
    "snapshot_id": "snapshot-example", "fingerprint": "a" * 64,
    "classification": "confirmed_defect", "category": "ui", "severity": "high", "confidence": "high",
    "title": "Synthetic example: submit button is obscured.",
    "expected": "The declared submit interaction can reach the button.",
    "expected_basis": "Synthetic acceptance criterion.",
    "actual": "A synthetic hit test selects the footer.",
    "locations": [{"path": "src/Form.tsx", "content_hash": "b" * 64, "line": 12}],
    "evidence": ["artifact-synthetic-hit-test"],
    "reproduction": {"check_id": "browser.hit_test", "instructions": "Run the configured synthetic mobile interaction."},
    "suggested_next_step": "Inspect positioning and rerun the interaction.",
    "verification_check_ids": ["browser.hit_test"], "freshness": "current",
    "created_at": "2026-10-12T12:00:00Z"
}
body_ref = {"root": "request_bodies", "path": "results/synthetic.json", "sha256": "a" * 64,
            "size_bytes": 100, "content_contract": "check_result"}
more_examples = [
    finding_example,
    {"contract": "feedback", "schema_version": "1.0", "finding_id": "finding-example",
     "outcome": "diagnosis_wrong", "reason": "Synthetic review rejects the original causal hypothesis.",
     "provenance": provenance},
    {"contract": "lesson", "schema_version": "1.0", "lesson_id": "lesson-example",
     "challenge_id": "challenge-example", "scope": "project", "status": "candidate",
     "summary": "Synthetic candidate: report versions need explicit parser negotiation.",
     "tags": ["parser"], "applicability": ["parser-version-example"],
     "evidence": ["artifact-synthetic-report"], "provenance": provenance},
    {"contract": "improvement", "schema_version": "1.0", "candidate_id": "candidate-example",
     "challenge_id": "challenge-example", "kind": "code", "base_version": "0.1.0",
     "base_package_sha256": "a" * 64, "proposed_sha256": "b" * 64,
     "evaluator_sha256": "c" * 64, "heldout_fixture_sha256": "d" * 64,
     "state": "proposed", "evaluation_passed": False, "created_at": "2026-10-12T12:00:00Z"},
    {"contract": "capabilities", "schema_version": "1.0", "host": "synthetic-host", "host_version": None,
     "status": "documented_not_tested", "delivery": "checkpoint",
     "available_check_ids": [], "blocked_check_ids": ["browser.hit_test"],
     "enforced_limits": [], "best_effort_limits": []},
    {"contract": "response", "schema_version": "1.0", "request_id": "12579465-3de1-4a16-bb40-3fac69bf6e83",
     "project_id": "project-example", "status": "incomplete", "run_ids": ["run-example"],
     "finding_ids": [], "completeness": "none", "reasons": ["Synthetic run discovered no tests."],
     "result_ref": body_ref, "created_at": "2026-10-12T12:00:00Z"},
    {"contract": "job_status", "schema_version": "1.0", "run_id": "run-example",
     "snapshot_id": "snapshot-example", "check_id": "python.pytest", "state": "finished",
     "completeness": "none", "result_ref": body_ref, "created_at": "2026-10-12T12:00:00Z"}
]
by_contract = {item["contract"]: item for item in examples}
by_contract.update({item["contract"]: item for item in more_examples})
write_json(examples_path, list(by_contract.values()))

requirements = (ROOT / "COMPANION_REQUIREMENTS.md").read_text(encoding="utf-8")
groups = {
    "A": ("Core/packaging/host contracts", "1–5, 14, 22", "P0/P3", "Boundary and compatibility fixtures"),
    "P": ("Discovery/config/impact graph", "9, 12, 21", "P0", "Representative manifest and unknown-stack fixtures"),
    "E": ("Coordinator/mailbox/scheduler/snapshots", "6–10, 15", "P2", "Replay, rapid-save, cancellation and resource tests"),
    "H": ("Host adapters/capabilities/delivery", "5, 14–15", "P3", "Real host/version delivery and fallback tests"),
    "F": ("Contracts/normalization/storage/findings", "8, 11, 13–14", "P0/P1", "Typed outcomes, freshness and evidence fixtures"),
    "R": ("Repair/verification/challenge workflow", "13, 16", "P1", "Reproduce, fix, verify, regression and retry cases"),
    "M": ("Challenges/memory/improvement", "16–17, 19", "P1/P5", "Journal, provenance, deletion, poisoning and rollback cases"),
    "S": ("Policy/runner/redaction/isolation", "11, 19, 21", "P0–P5", "Secrets, path, permission and side-effect cases"),
    "D": ("Distribution/installer/compatibility/cost", "2, 5, 15, 22", "P3", "Private package, upgrade/uninstall and spending-policy cases"),
    "Q": ("Test fixtures and companion reliability", "20, 23", "Every phase", "Independent observable behavior and failure cases"),
    "B": ("Held-out paired evaluation", "23", "P4", "Equal-budget measured quality/overhead/regression benchmark")
}
rows = []
for rid, description in re.findall(r"(?m)^- ([A-Z]\d{2}): (.+)$", requirements):
    module, sections, phase, acceptance = groups[rid[0]]
    safe_description = description.replace("|", "/")
    rows.append(f"| {rid} | {safe_description} | {module} | {sections} | {phase} | {acceptance} |")
packs = re.findall(r"(?m)^### (C\d{2}) [^\n]+", requirements)
plan = """# Implementation plan and requirement traceability

Status: architecture/build plan, not a completed runtime. All requirements start planned. A row becomes implemented only with reviewed code and its observable acceptance checks.

## Build phases

| Phase | Modules and deliverables | Completion gate |
|---|---|---|
| P0 | Contracts, config, storage/migrations, doctor, static discovery, CLI plan | Offline setup and schema/contract/error cases |
| P1 | Native check adapters, parsers/counts, snapshots, findings, verification, challenges, memory | Seeded/clean/blocked cases and current-revision verified repair |
| P2 | Mailbox, coordinator, scheduler, budgets, watch, cancellation, recovery | Crash replay, stale results, process cleanup and bounded load |
| P3 | Portable skill, MCP/host adapters, installer/removal, OS matrix | Actual host delivery/fallback and configuration preservation |
| P4 | Expanded detector packs and paired evaluation | Each advertised check has operational fixtures; held-out measured benefit |
| P5 | Candidate improvement, self-repair, activation/rollback, optional local training | Independent evaluation, privacy lineage, recovery and LKG rollback |

No phase authorizes publishing the private repository, installing a scheduler, accessing production, paying for services, or training on an unspecified dataset.

## Requirement coverage

The original requirement wording is preserved below. Architecture section numbers refer to ARCHITECTURE.md. The acceptance column identifies the test family; each implementation task must instantiate its precise behavior, inputs, and assertions.

| ID | Requirement | Implementation owner | Architecture sections | Phase | Acceptance family |
|---|---|---|---|---|---|
"""
plan += "\n".join(rows) + "\n"
plan += """
## Detector pack coverage

Every pack is specified in architecture section 12 and detailed in COMPANION_REQUIREMENTS.md. Packs are planned until their prerequisites, concrete adapters, seeded failures, clean fixtures, blocked/parser cases, permissions and cost limits are implemented.

| Pack | Owner | Phase | Required proof |
|---|---|---|---|
"""
for pack in packs:
    plan += f"| {pack} | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |\n"
plan += """
## Implementation invariants to preserve

- The coordinator alone owns writes and migrations; ledger and DDL commit atomically.
- Every observation matches its run/snapshot; every delivery matches its observation/finding.
- Events create/register required sessions atomically; event/request ID collisions cannot overwrite responses.
- Result freshness and required test counts are runtime proofs, not only schema enums.
- Resolved challenges require suitable verified current evidence.
- Candidate patches cannot edit their independently pinned evaluator or held-out acceptance set.
- Activation uses exact package/artifact hashes and DB-compatible rollback.
- Deletion/consent withdrawal propagates to lessons, datasets, exports and learned components.
- User data-use prohibitions and host permissions cannot be relaxed by repository/session overrides.
- Typed protocol validators and exported schemas must share conformance fixtures.

## Current validation boundary

tools/validate_architecture.py checks design syntax, known contract semantics, SQL integrity/constraints, optional FTS synchronization, migration atomicity, backup restoration, privacy/relation invariants, configuration defaults, and coverage of every requirement ID.

It is an architecture validation utility. It does not establish working watchers, supported live host integration, successful real-project checks, actual process isolation, maintenance automation, detector accuracy, or product superiority. Those need the runtime and acceptance phases above.
"""
(ROOT / "IMPLEMENTATION_PLAN.md").write_text(plan, encoding="utf-8")
print(f"Refined {len(root_contracts)} contracts; traced {len(rows)} requirements and {len(packs)} packs.")
