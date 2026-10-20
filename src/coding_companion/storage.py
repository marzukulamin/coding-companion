from __future__ import annotations

import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from importlib.resources import files
from pathlib import Path

from . import __version__
from .common import CompanionError, atomic_write, canonical, digest, file_digest, identifier, now, read_bounded, redact
from .config import Config, project_id
from .contracts import Check, Result
from .discovery import Snapshot


class Store:
    """Used exclusively inside coordinator ownership, including finite operations."""

    def __init__(self, root: Path, state: Path, config: Config):
        self.root, self.state, self.config = root, state, config
        self.project_id = project_id(root)
        db_path = state / "companion.sqlite"
        if db_path.is_symlink() or db_path.is_junction():
            raise CompanionError("State database cannot be linked")
        self.db = sqlite3.connect(db_path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.execute("PRAGMA journal_mode=DELETE")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA busy_timeout=3000")
            self.migrate()
            self.check_integrity()
            existing = self.db.execute("SELECT * FROM project").fetchone()
            if existing and (existing["project_id"] != self.project_id or existing["root_identity"] != str(root.resolve())):
                raise CompanionError("State belongs to a different project")
            if not existing:
                self.insert("project", singleton=1, project_id=self.project_id, root_identity=str(root.resolve()), display_name=root.name, created_at=now(), config_json=canonical({"policy_hash": config.fingerprint}))
            self.session_id = identifier()
            self.insert("sessions", session_id=self.session_id, project_id=self.project_id, host_name="manual_cli", host_version=None, adapter_version=__version__, capabilities_json=canonical({"mode": "checkpoint", "live_delivery": "unverified"}), policy_hash=config.fingerprint, started_at=now(), state="active")
            self.recover()
        except BaseException:
            self.db.close()
            raise

    def migrate(self) -> None:
        if sqlite3.sqlite_version_info < (3, 38, 0):
            raise CompanionError("SQLite >= 3.38 with JSON and STRICT support is required")
        self.db.execute("SELECT json_valid('{}')").fetchone()
        for version, filename in ((1, "001_initial.sql"), (2, "002_runtime.sql")):
            script = files("coding_companion").joinpath("resources/" + filename).read_text(encoding="utf-8")
            checksum = digest(script.encode())
            exists = self.db.execute("SELECT name FROM sqlite_master WHERE name='schema_migrations'").fetchone()
            if exists:
                applied = self.db.execute("SELECT checksum FROM schema_migrations WHERE version=?", (version,)).fetchone()
                if applied:
                    if applied[0] != checksum:
                        raise CompanionError("Migration checksum mismatch; preserve state and review upgrade")
                    continue
                if version == 1:
                    raise CompanionError("Missing initial migration ledger")
                backup = self.state / f"before-migration-{version}.sqlite"
                if backup.exists():
                    raise CompanionError("Prior upgrade backup exists; review interrupted upgrade before retry")
                with closing(sqlite3.connect(backup)) as target:
                    self.db.backup(target)
                    if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise CompanionError("Pre-upgrade backup failed integrity check")
            try:
                self.db.executescript("BEGIN IMMEDIATE;\n" + script)
                self.db.execute("INSERT INTO schema_migrations VALUES (?,?,?)", (version, checksum, now()))
                if self.db.execute("PRAGMA foreign_key_check").fetchall():
                    raise CompanionError("Migration foreign-key integrity failed")
                self.db.execute("COMMIT")
            except BaseException:
                if self.db.in_transaction:
                    self.db.execute("ROLLBACK")
                raise

    def check_budget(self):
        total = 0
        for path in self.state.rglob("*"):
            if path.is_symlink() or path.is_junction():
                raise CompanionError("Linked state entry rejected")
            if path.is_file():
                total += path.stat().st_size
            if total > self.config.max_state_bytes:
                raise CompanionError("Project state budget reached; archive/purge reviewed state before further checks")

    def check_privacy(self):
        marker = self.state / "privacy-epoch.json"
        if marker.exists() and json.loads(read_bounded(marker, 65536)).get("pending"):
            raise CompanionError("Privacy withdrawal is pending recovery; run maintenance or repeat the withdrawal before accessing diagnostics")

    def check_integrity(self):
        if self.db.execute("PRAGMA quick_check").fetchone()[0] != "ok" or self.db.execute("PRAGMA foreign_key_check").fetchall():
            raise CompanionError("Database integrity failed; state preserved")

    def insert(self, table: str, **values):
        # Identifiers originate only in source code; no SQL interface is exposed.
        columns = ",".join(values)
        self.db.execute(f"INSERT INTO {table} ({columns}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def recover(self):
        with self.transaction():
            self.db.execute("UPDATE sessions SET state='interrupted', ended_at=? WHERE session_id != ? AND state='active'", (now(), self.session_id))
            interrupted = self.db.execute("SELECT run_id,result_json FROM runs WHERE outcome IN ('queued','running')").fetchall()
            for row in interrupted:
                result = json.loads(row["result_json"])
                result.update(outcome="cancelled", completeness="none", reasons=["Coordinator interrupted; rerun required"])
                self.db.execute("UPDATE runs SET outcome='cancelled',completeness='none',ended_at=?,result_json=? WHERE run_id=?", (now(), canonical(result), row["run_id"]))
            self.db.execute("UPDATE events SET state='queued' WHERE state='processing'")

    def latest_snapshot_id(self):
        # Creation order is not observation order: source can return to old bytes.
        row = self.db.execute("SELECT snapshot_id FROM snapshots WHERE snapshot_id=(SELECT json_extract(config_json,'$.last_snapshot_id') FROM project WHERE singleton=1)").fetchone()
        if row:
            return row[0]
        legacy = self.db.execute("SELECT snapshot_id FROM snapshots ORDER BY created_at DESC LIMIT 1").fetchone()
        return legacy[0] if legacy else None

    def save_snapshot(self, snap: Snapshot):
        with self.transaction():
            self.db.execute("UPDATE snapshots SET state='historical' WHERE state IN ('current','partial') AND snapshot_id<>?", (snap.snapshot_id,))
            state = "current" if snap.complete else "partial"
            if self.db.execute("SELECT 1 FROM snapshots WHERE snapshot_id=?", (snap.snapshot_id,)).fetchone():
                self.db.execute("UPDATE snapshots SET state=? WHERE snapshot_id=?", (state, snap.snapshot_id))
            else:
                self.insert("snapshots", snapshot_id=snap.snapshot_id, manifest_hash=digest(snap.files), environment_hash=snap.environment_hash, policy_hash=snap.policy_hash, created_at=now(), coverage_json=canonical({"gaps": snap.gaps[:100], "provenance": snap.provenance}), state=state)
                self.db.executemany("INSERT INTO snapshot_files VALUES (?,?,?,?,?)", [(snap.snapshot_id, p, meta["hash"], meta["size"], Path(p).suffix) for p, meta in snap.files.items()])
            self.db.execute("UPDATE project SET config_json=json_set(config_json,'$.last_snapshot_id',?) WHERE singleton=1", (snap.snapshot_id,))

    def define_check(self, check: Check):
        manifest = canonical(check.manifest())
        self.db.execute("INSERT OR IGNORE INTO check_definitions VALUES (?,?,?,?,?,?)", (check.check_id, check.version, digest(manifest.encode()), manifest, canonical({"source": "explicit_user_native" if check.executable else "builtin"}), "approved"))

    def begin_run(self, result: Result, event_id: str | None = None, queued=False):
        self.insert("runs", run_id=result.run_id, event_id=event_id, session_id=self.session_id, snapshot_id=result.snapshot_id, check_id=result.check_id, check_version=result.check_version, started_at=None if queued else now(), outcome="queued" if queued else "running", completeness="none", result_json=canonical({"run_id": result.run_id}))

    def finish_run(self, result: Result, duration_ms: int):
        payload = result.json()
        with self.transaction():
            for artifact in result.artifacts:
                self.insert("artifacts", **artifact)
            self.db.execute("UPDATE runs SET ended_at=?,outcome=?,completeness=?,exit_code=?,discovered_count=?,executed_count=?,skipped_count=?,duration_ms=?,result_json=? WHERE run_id=?", (now(), result.outcome, result.completeness, result.exit_code, result.counts["discovered"], result.counts["executed"], result.counts["skipped"], duration_ms, canonical(payload), result.run_id))
            for item in result.findings:
                existing = self.db.execute("SELECT lifecycle FROM findings WHERE finding_id=?", (item["finding_id"],)).fetchone()
                if not existing:
                    self.insert("findings", **{k: item[k] for k in ("finding_id", "fingerprint", "category", "severity", "confidence", "classification", "rule_id", "rule_version", "title")}, lifecycle="new", first_seen_at=item["created_at"], last_seen_at=item["created_at"])
                else:
                    state = "reopened" if existing[0] == "verified_resolved" else existing[0]
                    self.db.execute("UPDATE findings SET lifecycle=?,last_seen_at=?,rule_version=?,severity=?,confidence=?,classification=?,title=? WHERE finding_id=?", (state, now(), item["rule_version"], item["severity"], item["confidence"], item["classification"], item["title"], item["finding_id"]))
                observation = identifier()
                self.insert("observations", observation_id=observation, finding_id=item["finding_id"], run_id=result.run_id, snapshot_id=result.snapshot_id, classification=item["classification"], rule_id=item["rule_id"], rule_version=item["rule_version"], severity=item["severity"], confidence=item["confidence"], location_json=canonical(item["locations"]), expected=item["expected"], expected_basis=item["expected_basis"], actual=item["actual"], evidence_json=canonical(item["evidence"]), reproduction_json=canonical(item["reproduction"]), remedy_json=canonical({"next_step": item["suggested_next_step"]}), verification_json=canonical({"checks": item["verification_check_ids"], "basis": result.verification_basis, "counts": result.counts}), created_at=item["created_at"], freshness=item["freshness"])
                for artifact_id in item["evidence"]:
                    self.insert("observation_artifacts", observation_id=observation, artifact_id=artifact_id, role="diagnostic")
                # Each observation remains immutable; callers can deduplicate by finding ID.
                self.insert("deliveries", session_id=self.session_id, finding_id=item["finding_id"], observation_id=observation, payload_hash=digest(item), status="pending", created_at=now())

    def findings(self, since: int = 0, limit: int = 100) -> dict:
        rows = self.db.execute("SELECT f.*,o.location_json,o.actual,o.expected,o.run_id,o.snapshot_id,o.freshness,d.delivery_id FROM deliveries d JOIN observations o ON o.observation_id=d.observation_id JOIN findings f ON f.finding_id=o.finding_id WHERE d.delivery_id>? ORDER BY d.delivery_id LIMIT ?", (since, limit)).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["locations"] = json.loads(item.pop("location_json"))
            suppression = self.db.execute("SELECT 1 FROM suppressions WHERE (finding_id=? OR rule_id=?) AND (expires_at IS NULL OR expires_at>?) LIMIT 1", (item["finding_id"], item["rule_id"], now())).fetchone()
            if not suppression:
                items.append(item)
        return {"findings": items, "next_cursor": rows[-1]["delivery_id"] if rows else since}

    def inspect(self, finding_id: str) -> dict:
        self.check_privacy()
        row = self.db.execute("SELECT * FROM findings WHERE finding_id=?", (finding_id,)).fetchone()
        if not row:
            raise CompanionError("Unknown finding")
        observation = self.db.execute("SELECT * FROM observations WHERE finding_id=? ORDER BY created_at DESC LIMIT 1", (finding_id,)).fetchone()
        item = dict(row)
        item["observation"] = dict(observation)
        for key in list(item["observation"]):
            if key.endswith("_json"):
                item["observation"][key[:-5]] = json.loads(item["observation"].pop(key))
        return item

    def status(self) -> dict:
        return {"project_id": self.project_id, "session_id": self.session_id, "state_path": str(self.state), "runs": self.db.execute("SELECT count(*) FROM runs").fetchone()[0], "active_findings": self.db.execute("SELECT count(*) FROM findings WHERE lifecycle NOT IN ('verified_resolved','dismissed','accepted_risk')").fetchone()[0], "interrupted_runs": self.db.execute("SELECT count(*) FROM runs WHERE outcome='cancelled'").fetchone()[0], "delivery": "cli_checkpoints", "limits": {"cpu": "not_enforced", "ram": "Windows_per_process_job_limit" if __import__('os').name == 'nt' else "not_enforced", "process_tree": "Windows_job_object" if __import__('os').name == 'nt' else "POSIX_process_group", "gpu": "no_gpu_use", "network": "static_checks_make_no_calls"}}

    def journal(self, actor: str, goal: str, symptoms: str, finding_id: str | None = None) -> str:
        if actor not in {"coding_agent", "companion", "user", "external_tool"}:
            raise CompanionError("Unknown challenge actor")
        challenge_id = identifier()
        self.insert("challenges", challenge_id=challenge_id, session_id=self.session_id, finding_id=finding_id, actor=actor, kind="diagnostic", stage="verification", goal=redact(goal)[:4000], symptoms=redact(symptoms)[:4000], constraints_json="{}", attempts_json="[]", hypotheses_json="[]", applicability_json=canonical({"project_id": self.project_id}), provenance_json=canonical({"actor": actor, "version": __version__}), evidence_json="[]", state="open", created_at=now(), updated_at=now())
        return challenge_id

    def challenges(self, actor: str = "all") -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT challenge_id,actor,goal,symptoms,state,created_at,verification_run_id FROM challenges WHERE (?='all' OR actor=?) ORDER BY created_at DESC LIMIT 100", (actor, actor))]

    def search_memory(self, query: str) -> list[dict]:
        self.check_privacy()
        if not self.config.memory_enabled:
            return []
        if not query or len(query) > 1000:
            raise CompanionError("Memory query must contain 1–1000 characters")
        from .discovery import environment_hash
        return [dict(r) for r in self.db.execute("SELECT lesson_id,summary,tags,verified_at,expires_at FROM lessons WHERE status='verified' AND scope='project' AND (expires_at IS NULL OR expires_at>?) AND json_extract(applicability_json,'$.policy_hash')=? AND json_extract(applicability_json,'$.environment_hash')=? AND json_extract(applicability_json,'$.companion_version')=? AND instr(lower(summary),lower(?))>0 ORDER BY verified_at DESC LIMIT 5", (now(), self.config.fingerprint, environment_hash(), __version__, query))]

    def save_lesson(self, finding_id: str, run_id: str, summary: str) -> str:
        if not self.config.memory_enabled:
            raise CompanionError("Memory disabled")
        lesson_id = identifier()
        expiry = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat().replace("+00:00", "Z")
        environment = self.db.execute("SELECT s.environment_hash FROM runs r JOIN snapshots s ON s.snapshot_id=r.snapshot_id WHERE r.run_id=?", (run_id,)).fetchone()
        if not environment:
            raise CompanionError("Lesson verification run is unavailable")
        self.insert("lessons", lesson_id=lesson_id, scope="project", status="verified", summary=redact(summary)[:4000], tags="verified_repair", applicability_json=canonical({"project_id": self.project_id, "policy_hash": self.config.fingerprint, "environment_hash": environment[0], "companion_version": __version__}), provenance_json=canonical({"version": __version__, "actor": "explicit_caller"}), evidence_json=canonical({"finding_id": finding_id, "verification_run_id": run_id}), privacy_class="project_private", verified_at=now(), expires_at=expiry, created_at=now())
        return lesson_id

    def delete_lesson(self, lesson_id: str):
        from .maintenance import withdraw
        return withdraw(self, "lesson", lesson_id)

    def audit(self, action: str, kind: str, entity_id: str):
        self.insert("audit_entries", session_id=self.session_id, actor="companion", action=action, entity_type=kind, entity_id=entity_id, details_json="{}", created_at=now())

    def backup(self, destination: Path):
        if destination.exists():
            raise CompanionError("Backup destination must not already exist")
        with closing(sqlite3.connect(destination)) as target:
            self.db.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise CompanionError("Backup integrity failed")
        self.insert("exports", export_id=identifier(), kind="backup", absolute_path=str(destination.resolve()), sha256=file_digest(destination, self.config.max_state_bytes), lineage_json=canonical({"scope": "project_state", "project_id": self.project_id}), state="available", created_at=now())

    def export_memory(self, destination: Path):
        if destination.exists():
            raise CompanionError("Export destination must not already exist")
        lessons = [dict(r) for r in self.db.execute("SELECT * FROM lessons WHERE status='verified' LIMIT 100")]
        body = canonical({"scope": "project_private", "lessons": lessons}).encode()
        atomic_write(destination, body)
        self.insert("exports", export_id=identifier(), kind="memory", absolute_path=str(destination.resolve()), sha256=digest(body), lineage_json=canonical({"lesson_ids": [item["lesson_id"] for item in lessons]}), state="available", created_at=now())
        return {"status": "complete", "output": str(destination.resolve()), "lessons": len(lessons)}

    def close(self):
        self.db.execute("UPDATE sessions SET state='ended',ended_at=? WHERE session_id=?", (now(), self.session_id))
        self.db.close()
