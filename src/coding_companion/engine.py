from __future__ import annotations

import json
import time
import threading
from types import SimpleNamespace

from .checks import CHECKS, plan, run_static
from .common import CompanionError, canonical, digest, now
from .contracts import Result
from .discovery import Snapshot, snapshot
from .impact import affected
from .native import input_context, load_probes, native_check, run_native
from .scheduler import Job, Scheduler
from .mailbox import stop_requested


class Engine:
    def __init__(self, store):
        self.store = store
        self.last_basis = {}

    def snapshot(self):
        self.store.check_privacy()
        self.store.check_budget()
        snap = snapshot(self.store.root, self.store.config, self.store.state)
        self.store.save_snapshot(snap)
        return snap

    def bind_native(self, snap, records):
        if not records:
            return snap
        context = input_context(records, self.store.root)
        return Snapshot(digest({"workspace": snap.snapshot_id, "native_inputs": context}), snap.files, snap.contents, snap.gaps, snap.environment_hash, snap.policy_hash, {"workspace_snapshot_id": snap.snapshot_id, "native_inputs": context})

    def snapshot_for_checks(self, selected):
        snap = self.snapshot()
        probes = load_probes(self.store.state)
        bound = self.bind_native(snap, {c: probes[c] for c in selected if c in probes})
        self.store.save_snapshot(bound)
        return bound

    def scoped_snapshot(self, scope="project"):
        previous = self.store.latest_snapshot_id()
        baseline = {r[0]: r[1] for r in self.store.db.execute("SELECT relative_path,content_hash FROM snapshot_files WHERE snapshot_id=?", (previous,))} if previous else {}
        snap = self.snapshot()
        changed = sorted({p for p in snap.files if snap.files[p]["hash"] != baseline.get(p)} | (set(baseline) - set(snap.files)))
        route = affected(snap, changed) if scope == "changed" and previous else {"paths": sorted(snap.files), "scope": "project", "reason": "Explicit project scope or initial baseline", "changed": changed}
        subset = Snapshot(snap.snapshot_id, {p: snap.files[p] for p in route["paths"]}, {p: snap.contents[p] for p in route["paths"]}, snap.gaps, snap.environment_hash, snap.policy_hash)
        return subset, route

    def plan(self, selected=None, scope="project"):
        snap, route = self.scoped_snapshot(scope)
        static = [c for c in selected if c in CHECKS] if selected else None
        result = plan(snap, static)
        probes = load_probes(self.store.state)
        native_ids = [c for c in selected or [] if c not in CHECKS]
        for check_id in native_ids:
            if check_id not in probes:
                raise CompanionError("Unknown or untrusted check ID")
            result["checks"].append({**native_check(probes[check_id]).manifest(), "status": "trust_rechecked_at_execution"})
        result.update(requested_scope=scope, effective_scope=route["scope"], scope_reason=route["reason"], changed_paths=route["changed"][:1000], affected_paths=route["paths"][:1000])
        return result

    def check(self, selected=None, event_id=None, scope="project", reuse=False) -> dict:
        selected = list(dict.fromkeys(selected or ["python.syntax", "structured.formats"]))
        probes = load_probes(self.store.state)
        if len(selected) > 100 or any(c not in CHECKS and c not in probes for c in selected):
            raise CompanionError("Unknown check ID or plan limit exceeded")
        snap, route = self.scoped_snapshot(scope)
        if reuse:
            cached = []
            complete_paths = [r[0] for r in self.store.db.execute("SELECT relative_path FROM snapshot_files WHERE snapshot_id=?", (snap.snapshot_id,))]
            for check_id in selected:
                row = self.store.db.execute("SELECT result_json FROM runs WHERE snapshot_id=? AND check_id=? AND outcome IN ('passed','failed','not_applicable') ORDER BY ended_at DESC LIMIT 1", (snap.snapshot_id, check_id)).fetchone()
                if row:
                    result = json.loads(row[0])
                    if check_id in {"python.syntax", "structured.formats"}:
                        expected_count = sum(any(p.endswith(suffix) for suffix in CHECKS[check_id].suffixes) for p in complete_paths)
                        if result["counts"]["discovered"] == expected_count and result["check_version"] == CHECKS[check_id].version and (result["completeness"] == "complete" or result["outcome"] == "not_applicable"):
                            cached.append(result)
            if len(cached) == len(selected) and any(r["completeness"] == "complete" for r in cached):
                return {"status": "failed" if any(r["outcome"] == "failed" for r in cached) else "complete", "completeness": "complete", "snapshot_id": snap.snapshot_id, "results": cached, "reused": True}
        # Native trust and execution bind the complete declared workspace inputs.
        selected_probes = {c: probes[c] for c in selected if c in probes}
        native_snap = snapshot(self.store.root, self.store.config, self.store.state) if selected_probes else snap
        if selected_probes:
            native_snap = self.bind_native(native_snap, selected_probes)
            self.store.save_snapshot(native_snap)
            snap = Snapshot(native_snap.snapshot_id, snap.files, snap.contents, snap.gaps, snap.environment_hash, snap.policy_hash, native_snap.provenance)
        results = {}
        scheduler = Scheduler(self.store.config)
        interrupted = threading.Event()
        def cancelled():
            return interrupted.is_set() or stop_requested(self.store.state, self.store.project_id)
        worker_context = SimpleNamespace(root=self.store.root, state=self.store.state, config=self.store.config, cancel=cancelled)
        for check_id in selected:
            definition = CHECKS[check_id] if check_id in CHECKS else native_check(probes[check_id])
            self.store.define_check(definition)
            placeholder = Result(check_id, snap.snapshot_id, "blocked", "none", {"discovered": None, "executed": None, "skipped": None})
            placeholder.check_version = definition.version
            self.store.begin_run(placeholder, event_id, queued=True)
            execute = (lambda cid=check_id, rid=placeholder.run_id: run_static(cid, snap, rid)) if check_id in CHECKS else (lambda cid=check_id, rid=placeholder.run_id: run_native(worker_context, probes[cid], native_snap, rid))
            scheduler.enqueue(Job(f"{check_id}:{snap.snapshot_id}", "expensive" if definition.executable else "fast", 10, time.monotonic(), execute, placeholder))

        def started(job):
            self.store.db.execute("UPDATE runs SET outcome='running',started_at=? WHERE run_id=?", (now(), job.payload.run_id))

        def finished(job, result, error, duration_ms):
            placeholder = job.payload
            if result is None:
                result = placeholder
                result.outcome = "execution_error" if error else "cancelled"
                result.reasons = [str(error)[:2000]] if error else ["Pending check cancelled before execution"]
            current = snapshot(self.store.root, self.store.config, self.store.state)
            current = self.bind_native(current, selected_probes)
            if current.snapshot_id != snap.snapshot_id and result.outcome != "cancelled":
                result.outcome, result.completeness = "superseded", "partial"
                result.reasons.append("Inputs changed while the check ran")
                for item in result.findings:
                    item["freshness"] = "stale"
            self.store.finish_run(result, duration_ms)
            self.last_basis[result.check_id] = result.verification_basis
            results[result.check_id] = result.json()
        try:
            scheduler.run(started, finished, cancelled, interrupted.set)
        except BaseException:
            interrupted.set()
            raise
        results = [results[check_id] for check_id in selected]
        complete = all(r["completeness"] == "complete" or r["outcome"] == "not_applicable" for r in results)
        if all(r["outcome"] == "not_applicable" for r in results):
            complete = False
        defects = any(r["outcome"] == "failed" for r in results)
        return {"schema_version": "1.0", "project_id": self.store.project_id, "snapshot_id": snap.snapshot_id, "status": "failed" if defects else "complete" if complete else "incomplete", "completeness": "complete" if complete else "partial", "results": results, "coverage_scope": "Selected checks only", "effective_scope": route["scope"], "scope_reason": route["reason"], "changed_paths": route["changed"][:1000], "created_at": now()}

    def verify(self, finding_id: str, lesson: str | None = None) -> dict:
        item = self.store.inspect(finding_id)
        observation = item["observation"]
        checks = observation["verification"]["checks"]
        snap = self.snapshot()
        # Removal/renaming cannot silently stand in for a proven repair.
        if any(loc["path"] not in snap.files for loc in observation["location"]):
            raise CompanionError("Finding input removed; verification requires an explicit replacement contract")
        if item["rule_id"] == "structured.formats":
            # Changing extensions to evade the parser is not verified resolution.
            if not all(loc["path"].endswith((".json", ".toml")) for loc in observation["location"]):
                raise CompanionError("Original format no longer verified")
        report = self.check(checks)
        passed = report["completeness"] == "complete" and all(r["outcome"] == "passed" for r in report["results"])
        original = observation["verification"].get("basis", {})
        current_basis = self.last_basis.get(checks[0], {})
        unchanged = True
        if original.get("command_hash") and original["command_hash"] != current_basis.get("command_hash"):
            unchanged = False
        if original.get("case_ids") and not set(original["case_ids"]).issubset(set(current_basis.get("case_ids", []))):
            unchanged = False
        if not set(original.get("failed_case_ids", [])).issubset(set(current_basis.get("executed_case_ids", []))):
            unchanged = False
        if original.get("acceptance_hashes") and original["acceptance_hashes"] != current_basis.get("acceptance_hashes"):
            unchanged = False
        if any(current_basis.get("test_contract_hashes", {}).get(key) != value for key, value in original.get("test_contract_hashes", {}).items()):
            unchanged = False
        if not unchanged:
            passed = False
            report["verification_blocker"] = "Original acceptance criteria, command or required test cases changed; review the changed contract rather than asserting repair"
        fresh = self.snapshot_for_checks(checks).snapshot_id == report["snapshot_id"]
        if passed and fresh:
            with self.store.transaction():
                self.store.db.execute("UPDATE findings SET lifecycle='verified_resolved' WHERE finding_id=?", (finding_id,))
                run_id = report["results"][0]["run_id"]
                self.store.db.execute("UPDATE challenges SET state='resolved',resolution='Verified current repair',verification_run_id=?,updated_at=? WHERE finding_id=? AND state IN ('open','blocked')", (run_id, now(), finding_id))
                self.store.audit("verified_resolution", "finding", finding_id)
                if lesson:
                    report["lesson_id"] = self.store.save_lesson(finding_id, run_id, lesson)
            report["resolution"] = "verified_resolved"
        else:
            report["resolution"] = "unresolved"
        return report

    def refresh_findings(self):
        snap = self.snapshot()
        probes = load_probes(self.store.state)
        native_ids = {}
        for row in self.store.db.execute("SELECT o.observation_id,o.location_json,o.snapshot_id,r.check_id,s.environment_hash,s.policy_hash,s.coverage_json FROM observations o JOIN runs r ON r.run_id=o.run_id JOIN snapshots s ON s.snapshot_id=o.snapshot_id WHERE o.freshness='current'").fetchall():
            locations = json.loads(row["location_json"])
            stale = any(snap.files.get(loc["path"], {}).get("hash") != loc["content_hash"] for loc in locations)
            stale |= row["environment_hash"] != snap.environment_hash or row["policy_hash"] != snap.policy_hash
            if row["check_id"].startswith("native."):
                context = json.loads(row["coverage_json"]).get("provenance", {}).get("native_inputs", {})
                keys = tuple(sorted(context))
                if keys not in native_ids:
                    native_ids[keys] = self.bind_native(snap, {c: probes[c] for c in keys if c in probes}).snapshot_id
                stale |= row["snapshot_id"] != native_ids[keys]
            if stale:
                self.store.db.execute("UPDATE observations SET freshness='stale' WHERE observation_id=?", (row["observation_id"],))
