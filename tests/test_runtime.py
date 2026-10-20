from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from coding_companion.checks import run_static
from coding_companion.cli import Dispatcher, doctor, exit_code, invoke, main, parser
from coding_companion.common import CompanionError, atomic_write, canonical, digest, identifier, now, redact
from coding_companion.config import Config, load_config, project_id, state_root
from coding_companion.contracts import Result
from coding_companion.discovery import discover, snapshot
from coding_companion.engine import Engine
from coding_companion.host import manage_host
from coding_companion.improvement import manage_improvement
from coding_companion.mailbox import Mailbox, validate
from coding_companion.native import approve, load_probes
from coding_companion.ownership import Busy, Ownership
from coding_companion.parsers import junit, sarif
from coding_companion.storage import Store
from tools.validate_architecture import validate as schema_validate, SCHEMA


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "project"
        self.root.mkdir()
        self.state = self.base / "state"
        self.config = Config()
        self.owner = Ownership(self.state).__enter__()
        self.store = Store(self.root, self.state, self.config)
        self.engine = Engine(self.store)

    def tearDown(self):
        self.store.close()
        self.owner.__exit__()
        self.temp.cleanup()

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def seed(self):
        self.write("main.py", "def broken(:\n    pass\n")
        report = self.engine.check(["python.syntax"])
        return report["results"][0]["findings"][0]["finding_id"]

    def native_spec(self, script: str, category="build", parser="exit_code"):
        self.write("probe.py", script)
        self.engine.snapshot()
        spec = {"check_id": "native.fixture", "argv": [sys.executable, "probe.py", "{artifact_dir}"], "inputs": ["probe.py"], "parser": parser, "report": "tests.xml" if parser == "junit" else None, "category": category}
        return approve(self.store, spec)

    def test_doctor_real_runtime(self):
        self.assertEqual(doctor()["status"], "passed")
        self.assertFalse(doctor()["model_api_required"])

    def test_default_plan_clean_scan_shared_schema(self):
        self.write("main.py", "x = 1\n")
        self.write("package.json", '{"name":"fixture","scripts":{"test":"dangerous command"}}')
        report = self.engine.check()
        self.assertEqual(report["status"], "complete")
        for result in report["results"]:
            schema_validate(result, SCHEMA)
        inventory = discover(self.root, self.config)
        self.assertEqual(inventory["commands"][0]["trust"], "unreviewed")

    def test_seed_dedupe_immutable_observation_schema(self):
        fid = self.seed()
        report = self.engine.check(["python.syntax"])
        schema_validate(report["results"][0], SCHEMA)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM findings").fetchone()[0], 1)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM observations").fetchone()[0], 2)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.db.execute("UPDATE observations SET actual='changed' WHERE finding_id=?", (fid,))

    def test_python_compile_catches_contextual_syntax(self):
        self.write("main.py", "return 1\n")
        self.assertEqual(self.engine.check(["python.syntax"])["status"], "failed")

    def test_python_check_never_imports_source(self):
        marker = self.base / "executed"
        self.write("main.py", f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n")
        self.assertEqual(self.engine.check(["python.syntax"])["status"], "complete")
        self.assertFalse(marker.exists())

    def test_fix_verify_and_verified_memory(self):
        fid = self.seed()
        self.write("main.py", "def fixed():\n    return 1\n")
        report = self.engine.verify(fid, "Use valid Python function parameters")
        self.assertEqual(report["resolution"], "verified_resolved")
        self.assertEqual(len(self.store.search_memory("parameters")), 1)
        self.store.delete_lesson(report["lesson_id"])
        self.assertEqual(self.store.search_memory("parameters"), [])

    def test_deleted_input_cannot_verify(self):
        fid = self.seed()
        (self.root / "main.py").unlink()
        with self.assertRaises(CompanionError):
            self.engine.verify(fid)
        self.assertNotEqual(self.store.inspect(fid)["lifecycle"], "verified_resolved")

    def test_recurrence_reopens_finding(self):
        fid = self.seed()
        self.write("main.py", "x=1")
        self.engine.verify(fid)
        self.write("main.py", "x = (")
        self.engine.check(["python.syntax"])
        self.assertEqual(self.store.inspect(fid)["lifecycle"], "reopened")

    def test_stale_finding_before_delivery(self):
        fid = self.seed()
        self.write("main.py", "x=1")
        self.engine.refresh_findings()
        self.assertEqual(self.store.inspect(fid)["observation"]["freshness"], "stale")

    def test_changed_during_check_superseded(self):
        self.write("main.py", "x=1")
        original = run_static
        def change(check_id, snap, run_id):
            result = original(check_id, snap, run_id)
            self.write("main.py", "x=2")
            return result
        with patch("coding_companion.engine.run_static", side_effect=change):
            report = self.engine.check(["python.syntax"])
        self.assertEqual(report["results"][0]["outcome"], "superseded")
        self.assertEqual(exit_code(report), 2)

    def test_empty_project_not_false_pass(self):
        report = self.engine.check()
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(exit_code(report), 2)

    def test_invalid_formats(self):
        self.write("bad.json", '{"a":}')
        self.write("bad.toml", "key=[")
        result = self.engine.check(["structured.formats"])["results"][0]
        self.assertEqual(len(result["findings"]), 2)
        schema_validate(result, SCHEMA)

    def test_limits_produce_partial(self):
        self.write("a.py", "x=1")
        self.write("b.py", "x=2")
        snap = snapshot(self.root, Config(max_files=1))
        self.assertFalse(snap.complete)
        self.assertEqual(run_static("python.syntax", snap).outcome, "inconclusive")

    def test_inventory_total_byte_budget(self):
        self.write("a.py", "x=1" * 100)
        snap = snapshot(self.root, Config(max_inventory_bytes=10))
        self.assertFalse(snap.complete)

    def test_secrets_and_generated_inputs_excluded(self):
        self.write(".env", "PASSWORD=CANARY_PRIVATE")
        self.write("node_modules/bad.py", "bad(")
        self.write("src/real.py", "x=1")
        snap = self.engine.snapshot()
        self.assertEqual(set(snap.files), {"src/real.py"})
        self.assertNotIn("CANARY_PRIVATE", canonical(snap.files))

    def test_state_excluded_from_own_inventory(self):
        state = self.root / "local-state"
        state.mkdir()
        (state / "bad.json").write_text("{", encoding="utf-8")
        self.write("main.py", "x=1")
        self.assertEqual(set(snapshot(self.root, self.config, state).files), {"main.py"})

    def test_config_no_permission_escalation(self):
        path = self.base / "config.toml"
        path.write_text("[execution]\nremote_network=true", encoding="utf-8")
        with self.assertRaises(CompanionError):
            load_config(path)
        path.write_text("[resources]\nmax_files=10\npoll_seconds=0.1", encoding="utf-8")
        self.assertEqual(load_config(path).max_files, 10)

    def test_config_rejects_boolean_as_integer(self):
        path = self.base / "config.toml"
        path.write_text("[resources]\nmax_files=true", encoding="utf-8")
        with self.assertRaises(CompanionError):
            load_config(path)

    def test_project_state_roots_separate(self):
        other = self.base / "another"
        other.mkdir()
        self.assertNotEqual(state_root(self.root, self.base), state_root(other, self.base))

    def test_database_rejects_foreign_project(self):
        other = self.base / "another"
        other.mkdir()
        with self.assertRaises(CompanionError):
            Store(other, self.state, self.config)

    def test_database_checksum_guard(self):
        self.store.db.execute("UPDATE schema_migrations SET checksum='bad'")
        with self.assertRaises(CompanionError):
            self.store.migrate()

    def test_migration_rollback_with_fault(self):
        fresh = self.base / "new-state"
        fresh.mkdir()
        class BrokenResource:
            def joinpath(self, path):
                return self
            def read_text(self, **kwargs):
                return "CREATE TABLE schema_migrations(version INTEGER, checksum TEXT, applied_at TEXT); CREATE TABLE should_rollback(id INTEGER); INVALID SQL;"
        with patch("coding_companion.storage.files", return_value=BrokenResource()):
            with self.assertRaises(sqlite3.Error):
                Store(self.root, fresh, self.config)
        with closing(sqlite3.connect(fresh / "companion.sqlite")) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='should_rollback'").fetchone())

    def test_backup_restores_integrity(self):
        self.seed()
        backup = self.base / "backup.sqlite"
        self.store.backup(backup)
        with closing(sqlite3.connect(backup)) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("SELECT count(*) FROM findings").fetchone()[0], 1)

    def test_os_lock_is_exclusive(self):
        with self.assertRaises(Busy):
            with Ownership(self.state):
                pass

    def test_zero_tests_rejected_runtime_and_schema(self):
        result = Result("python.syntax", digest(b"fixture"), "passed", "complete", {"discovered": 0, "executed": 0, "skipped": 0})
        with self.assertRaises(CompanionError):
            result.json()
        with self.assertRaises(CompanionError):
            junit(b'<testsuite tests="0"/>')

    def test_junit_counts_skips_and_failures(self):
        parsed = junit(b'<testsuite tests="3"><testcase/><testcase><skipped/></testcase><testcase><failure/></testcase></testsuite>')
        self.assertEqual(parsed["counts"], {"discovered": 3, "executed": 2, "skipped": 1})
        self.assertEqual(parsed["failed"], 1)

    def test_junit_entity_count_and_all_skip_rejected(self):
        for xml in (b'<!DOCTYPE x [<!ENTITY y SYSTEM "file:///etc/passwd">]><testsuite/>', b'<testsuite tests="3"><testcase/></testsuite>', b'<testsuite><testcase><skipped/></testcase></testsuite>', b'<invalid>'):
            with self.subTest(xml=xml), self.assertRaises(CompanionError):
                junit(xml)

    def test_sarif_missing_results_cannot_pass(self):
        with self.assertRaises(CompanionError):
            sarif(b'{"version":"2.1.0","runs":[{}]}')

    def test_native_real_clean_command_and_redaction(self):
        self.native_spec("print('api_key=CANARY_PRIVATE')\n")
        result = self.engine.check(["native.fixture"])["results"][0]
        self.assertEqual(result["outcome"], "passed")
        text = (self.state / "artifacts" / result["run_id"] / "output.txt").read_text()
        self.assertNotIn("CANARY_PRIVATE", text)

    def test_native_real_junit(self):
        script = "import sys\nfrom pathlib import Path\nPath(sys.argv[1], 'tests.xml').write_text('<testsuite tests=\"1\"><testcase/></testsuite>')\n"
        self.native_spec(script, "tests", "junit")
        result = self.engine.check(["native.fixture"])["results"][0]
        self.assertEqual(result["outcome"], "passed")
        self.assertEqual(result["counts"]["executed"], 1)
        schema_validate(result, SCHEMA)

    def test_native_changed_input_revokes_effective_trust(self):
        self.native_spec("print('hello')")
        self.write("probe.py", "print('changed')")
        report = self.engine.check(["native.fixture"])
        self.assertEqual(report["results"][0]["outcome"], "blocked")

    def test_native_test_exit_code_alone_rejected(self):
        with self.assertRaises(CompanionError):
            self.native_spec("print('ok')", "tests", "exit_code")

    def test_native_failure_not_application_defect_claim(self):
        self.native_spec("raise SystemExit(3)")
        result = self.engine.check(["native.fixture"])["results"][0]
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["findings"][0]["classification"], "check_failure")

    def test_native_missing_junit_is_execution_error(self):
        self.native_spec("print('no report')", "tests", "junit")
        self.assertEqual(self.engine.check(["native.fixture"])["results"][0]["outcome"], "execution_error")

    def test_native_timeout_and_output_limit_not_pass(self):
        self.native_spec("import time\ntime.sleep(10)")
        self.store.config = Config(timeout_seconds=1)
        result = self.engine.check(["native.fixture"])["results"][0]
        self.assertEqual(result["outcome"], "inconclusive")
        self.assertIn("timed out", result["reasons"][0])
        self.native_spec("print('X'*100000)")
        self.store.config = Config(max_output_bytes=100)
        result = self.engine.check(["native.fixture"])["results"][0]
        self.assertEqual(result["outcome"], "inconclusive")

    def request(self, operation="status", args=None):
        return {"schema_version": "1.0", "request_id": identifier(), "project_id": self.store.project_id, "operation": operation, "args": args or {}, "created_at": now(), "deadline_at": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat().replace("+00:00", "Z")}

    def enqueue(self, mailbox, request):
        path = self.state / "inbox" / f"{request['request_id']}.json"
        atomic_write(path, canonical(request).encode())
        mailbox.drain()
        response_path = self.state / "responses" / f"{request['request_id']}.json"
        return json.loads(response_path.read_text()) if response_path.exists() else None

    def test_mailbox_replay_and_collision(self):
        mailbox = Mailbox(self.store, Dispatcher(self.engine))
        request = self.request()
        first = self.enqueue(mailbox, request)
        self.assertEqual(first, self.enqueue(mailbox, request))
        request["operation"] = "stop"
        self.assertEqual(first, self.enqueue(mailbox, request))
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM events").fetchone()[0], 1)

    def test_mailbox_forbids_foreign_and_arbitrary_commands(self):
        request = self.request()
        request["args"] = {"argv": ["dangerous"]}
        with self.assertRaises(CompanionError):
            validate(request, self.store.project_id)
        request = self.request()
        request["project_id"] = "foreign"
        with self.assertRaises(CompanionError):
            validate(request, self.store.project_id)

    def test_mailbox_expiry_not_success(self):
        mailbox = Mailbox(self.store, Dispatcher(self.engine))
        request = self.request()
        request["deadline_at"] = "2020-01-01T00:00:00Z"
        self.assertEqual(self.enqueue(mailbox, request)["status"], "expired")

    def test_crash_replay_does_not_duplicate_execution(self):
        self.write("main.py", "x=1")
        dispatch = Dispatcher(self.engine)
        mailbox = Mailbox(self.store, dispatch)
        request = self.request("check", {"checks": ["python.syntax"]})
        self.enqueue(mailbox, request)
        self.store.db.execute("UPDATE events SET state='queued',result_json=NULL")
        response = self.state / "responses" / f"{request['request_id']}.json"
        response.unlink()
        mailbox.drain()
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM runs").fetchone()[0], 1)
        self.assertEqual(json.loads(response.read_text())["status"], "incomplete")

    def test_cursor_avoids_repeating_findings(self):
        self.seed()
        first = self.store.findings()
        self.assertTrue(first["findings"])
        self.assertEqual(self.store.findings(first["next_cursor"])["findings"], [])

    def test_sqlite_schema_dialect_opt_in(self):
        self.write("schema.sql", "CREATE TABLE t (id INTEGER PRIMARY KEY, body TEXT CHECK(length(body)>0)) STRICT;")
        report = self.engine.check(["sqlite.schema"])
        self.assertEqual(report["status"], "complete")
        self.write("schema.sql", "ATTACH DATABASE 'external.sqlite' AS other;")
        self.assertNotEqual(self.engine.check(["sqlite.schema"])["status"], "complete")
        self.assertFalse((self.root / "external.sqlite").exists())

    def test_host_install_preserves_existing_and_changed_files(self):
        target = self.base / "my-skill"
        result = manage_host("install", "manual", target)
        self.assertEqual(result["status"], "installed")
        with self.assertRaises(CompanionError):
            manage_host("install", "manual", target)
        (target / "extra.txt").write_text("preserve")
        manage_host("uninstall", "manual", target)
        self.assertEqual((target / "extra.txt").read_text(), "preserve")

    def test_host_uninstall_rejects_modified_owned_file(self):
        target = self.base / "my-skill"
        manage_host("install", "codex", target)
        (target / "SKILL.md").write_text("edited")
        with self.assertRaises(CompanionError):
            manage_host("uninstall", "codex", target)

    def test_lesson_candidate_evaluate_activate_rollback(self):
        fid = self.seed()
        self.write("main.py", "x=1")
        verified = self.engine.verify(fid)
        proposal = self.base / "lesson.json"
        proposal.write_text(canonical({"kind": "lesson", "summary": "Repair Python syntax before runtime checks", "finding_id": fid, "verification_run_id": verified["results"][0]["run_id"]}))
        args = SimpleNamespace(action="evaluate", proposal=proposal)
        candidate = manage_improvement(self.store, self.engine, args)["candidate_id"]
        with self.assertRaises(CompanionError):
            manage_improvement(self.store, self.engine, SimpleNamespace(action="activate", candidate=candidate, approve=False))
        active = manage_improvement(self.store, self.engine, SimpleNamespace(action="activate", candidate=candidate, approve=True))
        self.assertTrue(self.store.search_memory("syntax"))
        manage_improvement(self.store, self.engine, SimpleNamespace(action="rollback", candidate=candidate))
        self.assertEqual(self.store.search_memory("syntax"), [])

    def test_cli_flags_before_and_after_command(self):
        before = parser().parse_args(["--project", str(self.root), "status"])
        after = parser().parse_args(["status", "--project", str(self.root)])
        self.assertEqual(before.project, after.project)

    def test_cli_invalid_check_and_config_nonzero(self):
        with self.assertRaises(CompanionError):
            self.engine.check(["unknown"])
        self.assertEqual(exit_code({"status": "failed"}), 1)
        self.assertEqual(exit_code({"status": "blocked"}), 2)

    def test_secret_canaries_redacted(self):
        for value in ("api_key=CANARY_PRIVATE", "password:CANARY_PRIVATE", "https://user:CANARY_PRIVATE@example.com", "sk-CANARY_PRIVATE_123456789"):
            self.assertNotIn("CANARY_PRIVATE", redact(value))


class WatchIntegrationTests(unittest.TestCase):
    def test_real_watcher_mailbox_change_and_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "project"
            root.mkdir()
            source = root / "main.py"
            source.write_text("x=1")
            config_file = base / "config.toml"
            config_file.write_text("[resources]\npoll_seconds=0.05\ndebounce_seconds=0.1\nrequest_timeout_seconds=10")
            state_base = base / "state"
            state = state_root(root, state_base)
            config = load_config(config_file)
            process = subprocess.Popen([sys.executable, str(ROOT / "companion.py"), "watch", "--project", str(root), "--state-dir", str(state_base), "--config", str(config_file), "--max-seconds", "15"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 5
                while not (state / "owner.json").exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                report = invoke(root, state, config, "status", {})
                self.assertEqual(report["delivery"], "cli_checkpoints")
                source.write_text("x = (")
                deadline = time.monotonic() + 5
                items = []
                while time.monotonic() < deadline:
                    items = invoke(root, state, config, "findings", {})["findings"]
                    if items:
                        break
                    time.sleep(0.1)
                self.assertTrue(items)
                stop = invoke(root, state, config, "stop", {})
                self.assertEqual(stop["status"], "stopping")
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertIn("baseline", stderr)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                process.stdout.close()
                process.stderr.close()


if __name__ == "__main__":
    unittest.main()
