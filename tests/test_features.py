from __future__ import annotations

import json
import os
import sys
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import test_runtime as fixtures
from coding_companion.common import CompanionError, canonical, digest, now, redact
from coding_companion.config import Config
from coding_companion.discovery import InventoryCache, discover
from coding_companion.hooks import configuration, handle
from coding_companion.impact import affected
from coding_companion.learning import train, manage as learned
from coding_companion.maintenance import maintain, suppress, unsuppress, withdraw
from coding_companion.scheduler import Job, Scheduler
from coding_companion.updates import evaluate, installed_hash, manage as update, launch_active, wheel_validate
from coding_companion.evaluation import paired


class FeatureTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    tearDown = fixtures.RuntimeTests.tearDown
    write = fixtures.RuntimeTests.write
    seed = fixtures.RuntimeTests.seed
    native_spec = fixtures.RuntimeTests.native_spec

    def test_fair_scheduler_and_coalescing(self):
        scheduler = Scheduler(Config(aging_seconds=5))
        self.assertTrue(scheduler.enqueue(Job("old", "fast", 10, 0, lambda: None)))
        self.assertFalse(scheduler.enqueue(Job("old", "fast", 0, 100, lambda: None)))
        scheduler.enqueue(Job("new", "fast", 1, 100, lambda: None))
        self.assertEqual(scheduler.choose({"fast"}, clock=101).key, "old")

    def test_real_parallel_worker_limits(self):
        scheduler = Scheduler(Config(max_fast_workers=2, max_expensive_workers=1))
        counts, peaks, lock, completed = {"fast": 0, "expensive": 0}, {"fast": 0, "expensive": 0}, threading.Lock(), []
        def work(kind):
            with lock:
                counts[kind] += 1
                peaks[kind] = max(peaks[kind], counts[kind])
            time.sleep(0.03)
            with lock:
                counts[kind] -= 1
            return kind
        for i, kind in enumerate(["fast"] * 4 + ["expensive"] * 2):
            scheduler.enqueue(Job(str(i), kind, 10, time.monotonic(), lambda k=kind: work(k)))
        scheduler.run(lambda job: None, lambda job, result, error, duration: completed.append(result), lambda: False)
        self.assertEqual(len(completed), 6)
        self.assertEqual(peaks, {"fast": 2, "expensive": 1})

    def test_declared_requirements_and_services(self):
        self.write("src/app.py", "import os\nurl=os.environ['DATABASE_URL']")
        self.write("pyproject.toml", '[project]\nname="sample"\ndependencies=["fastapi", "psycopg>=3"]\n[tool.pytest.ini_options]\ntestpaths=["tests"]')
        self.write("companion.requirements.json", '{"acceptance_criteria":["tenant isolation"],"traffic":{"concurrency":10}}')
        result = discover(self.root, self.config)
        self.assertIn("fastapi", result["frameworks"])
        self.assertIn("DATABASE_URL", result["environment_names"])
        self.assertEqual(result["services"][0]["name"], "postgresql")
        self.assertNotIn("traffic", result["unknowns"])
        self.assertTrue(result["native_proposals"])

    def test_import_closure_and_broad_fallback(self):
        self.write("library.py", "value=1")
        self.write("consumer.py", "import library")
        self.write("other.py", "value=2")
        snap = self.engine.snapshot()
        self.assertEqual(affected(snap, ["library.py"])["paths"], ["consumer.py", "library.py"])
        self.write("package.json", "{}")
        self.assertEqual(affected(self.engine.snapshot(), ["package.json"])["scope"], "project")

    def test_changed_scope_scans_local_closure(self):
        self.write("library.py", "value=1")
        self.write("consumer.py", "import library")
        self.write("other.py", "value=2")
        self.engine.check(["python.syntax"])
        self.write("library.py", "value=3")
        report = self.engine.check(["python.syntax"], scope="changed")
        self.assertEqual(report["effective_scope"], "changed")
        self.assertEqual(report["results"][0]["counts"]["executed"], 2)
        full = self.engine.check(["python.syntax"], reuse=True)
        self.assertFalse(full.get("reused", False), "A scoped result must not be reused as a full-project proof")

    def test_poll_cache_reconciles_preserved_metadata(self):
        path = self.write("main.py", "value=1")
        cache = InventoryCache(reconcile_seconds=0.01)
        initial = cache.read(self.root, self.config, self.state)
        stat = path.stat()
        path.write_text("value=2")
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        time.sleep(0.02)
        self.assertNotEqual(initial.snapshot_id, cache.read(self.root, self.config, self.state).snapshot_id)

    def test_suppression_cursor_and_expiry(self):
        fid = self.seed()
        result = suppress(self.store, fid, "Accepted while requirements are clarified")
        page = self.store.findings()
        self.assertEqual(page["findings"], [])
        self.assertGreater(page["next_cursor"], 0)
        self.store.db.execute("UPDATE suppressions SET expires_at='2020-01-01T00:00:00Z'")
        maintain(self.store)
        self.assertNotEqual(self.store.inspect(fid)["lifecycle"], "accepted_risk")
        self.assertTrue(self.store.findings()["findings"])

    def test_withdraw_finding_scrubs_history_and_dependencies(self):
        fid = self.seed()
        self.write("main.py", "value=1")
        verified = self.engine.verify(fid, "Example lesson")
        cid = self.store.journal("user", "Example goal", "Example symptoms", fid)
        deleted = withdraw(self.store, "finding", fid)
        self.assertEqual(deleted["status"], "deleted")
        self.assertEqual(self.store.search_memory("Example"), [])
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM observations WHERE finding_id=?", (fid,)).fetchone()[0], 0)
        self.assertEqual(self.store.db.execute("SELECT symptoms FROM challenges WHERE challenge_id=?", (cid,)).fetchone()[0], "")
        self.store.check_integrity()

    def test_retention_removes_expired_evidence(self):
        self.native_spec("print('fixture output')")
        report = self.engine.check(["native.fixture"])
        path = self.state / "artifacts" / report["results"][0]["run_id"] / "output.txt"
        self.store.db.execute("UPDATE artifacts SET created_at='2020-01-01T00:00:00Z'")
        maintain(self.store)
        self.assertFalse(path.exists())

    def test_structured_secret_redaction(self):
        text = redact('{"api_key": "CANARY private value", "ok": 1}')
        self.assertNotIn("CANARY", text)
        self.assertEqual(json.loads(text)["ok"], 1)
        self.assertNotIn("CANARY", redact("Authorization: Bearer CANARY_PRIVATE"))

    def manifest_check(self, check_id, filename, data, expected="complete"):
        self.write(filename, canonical(data))
        result = self.engine.check([check_id])
        self.assertEqual(result["status"], expected, result)
        return result

    def test_data_pack_real_rows_and_orphans(self):
        self.write("rows.csv", "id,parent\n1,a\n2,b\n")
        data = {"datasets": [{"path": "rows.csv", "expected_rows": 2, "required_fields": ["id"], "unique_by": ["id"]}]}
        self.manifest_check("data.contracts", "companion.data.json", data)
        self.write("rows.csv", "id,parent\n1,a\n1,b\n")
        self.assertEqual(self.engine.check(["data.contracts"])["status"], "failed")

    def test_rag_pack_tenant_leak_and_staleness(self):
        data = {"embedding_dimension": 3, "documents": [{"id": "a", "tenant": "one", "version": 1}], "index": [{"document_id": "a", "tenant": "one", "version": 1, "dimension": 3}], "queries": [{"tenant": "one", "retrieved_document_ids": ["a"], "relevant_document_ids": ["a"]}]}
        self.manifest_check("rag.contracts", "companion.rag.json", data)
        data["queries"][0]["tenant"] = "two"
        self.manifest_check("rag.contracts", "companion.rag.json", data, "failed")

    def test_ai_pack_requires_actual_assertions(self):
        data = {"cases": [{"actual": {"answer": "yes", "citations": ["a"]}, "expected": {"required_fields": ["answer"], "allowed_citation_ids": ["a"]}}]}
        self.manifest_check("ai.contracts", "companion.evals.json", data)
        data["cases"][0]["expected"] = {"unknown_assertion": 1}
        self.manifest_check("ai.contracts", "companion.evals.json", data, "incomplete")

    def test_model_pack_exact_artifact_and_context(self):
        path = self.write("model.config", "fixture")
        data = {"model_id": "fixture", "revision": "v1", "license": "fixture rights", "tokenizer": "v1", "context_limit": 100, "prompt_tokens": 20, "max_new_tokens": 10, "artifacts": [{"path": "model.config", "sha256": digest(path.read_bytes())}]}
        self.manifest_check("model.contracts", "companion.model.json", data)
        data["max_new_tokens"] = 100
        self.manifest_check("model.contracts", "companion.model.json", data, "failed")

    def test_training_pack_split_leakage(self):
        data = {"seed": 1, "losses": [1.0, 0.5], "samples": [{"content_hash": digest(b"one"), "split": "train", "rights": "authorized", "consent": True}, {"content_hash": digest(b"two"), "split": "test", "rights": "authorized", "consent": True}]}
        self.manifest_check("training.contracts", "companion.training.json", data)
        data["samples"][1]["content_hash"] = data["samples"][0]["content_hash"]
        self.manifest_check("training.contracts", "companion.training.json", data, "failed")

    def test_measured_performance_pack_and_missing_workload(self):
        data = {"captured_revision": "fixture-v1", "workload": {"duration_seconds": 10, "concurrency": 2}, "latency_ms": [10, 20, 30], "errors": 0, "thresholds": {"p95_ms": 40}}
        self.manifest_check("performance.contracts", "companion.metrics.json", data)
        data["latency_ms"][-1] = 100
        self.manifest_check("performance.contracts", "companion.metrics.json", data, "failed")
        del data["workload"]
        self.manifest_check("performance.contracts", "companion.metrics.json", data, "incomplete")

    def test_heuristics_remain_predicted_risks(self):
        self.write("main.py", "eval(input())")
        self.write("index.html", '<img src="x.png"><div id="one"></div><div id="one"></div>')
        report = self.engine.check(["security.patterns", "web.semantics"])
        self.assertEqual(report["status"], "failed")
        self.assertTrue(all(f["classification"] == "predicted_risk" for r in report["results"] for f in r["findings"]))

    def ranking_dataset(self, challenge=None):
        samples = [("bug broken fatal crash", 1, "train"), ("bug critical broken defect", 1, "train"), ("clean passed healthy okay", 0, "train"), ("healthy good clean completed", 0, "train"), ("bug fatal broken failure", 1, "validation"), ("healthy clean completed success", 0, "validation"), ("critical broken bug outage", 1, "test"), ("good passed clean success", 0, "test")]
        rows = [{"text": text, "label": label, "split": split, **({"challenge_id": challenge} if challenge else {})} for text, label, split in samples]
        path = self.base / "dataset.json"
        path.write_text(canonical({"authorization": {"scope": "local_project", "rights": "authorized", "consent": True}, "samples": rows}))
        return path

    def test_local_ranking_requires_authorization_and_heldout(self):
        path = self.ranking_dataset()
        with self.assertRaises(CompanionError):
            train(self.store, path, False)
        result = train(self.store, path, True)
        self.assertEqual(result["status"], "evaluated")
        lid = result["learned_artifact_id"]
        with self.assertRaises(CompanionError):
            learned(self.store, "activate", lid)
        learned(self.store, "activate", lid, approve=True)
        self.assertGreater(learned(self.store, "score", lid, "critical bug failure")["probability"], 0.5)
        learned(self.store, "revoke", lid)
        with self.assertRaises(CompanionError):
            learned(self.store, "score", lid, "critical bug")

    def test_withdraw_training_lineage_retires_model(self):
        challenge = self.store.journal("user", "fixture goal", "fixture symptoms")
        result = train(self.store, self.ranking_dataset(challenge), True)
        lid = result["learned_artifact_id"]
        learned(self.store, "activate", lid, approve=True)
        withdraw(self.store, "challenge", challenge)
        self.assertEqual(self.store.db.execute("SELECT state FROM learned_artifacts WHERE learned_artifact_id=?", (lid,)).fetchone()[0], "deleted")
        with self.assertRaises(CompanionError):
            learned(self.store, "score", lid, "bug")

    def test_hook_configuration_only_information_and_project_binding(self):
        config = configuration(__import__('sys').executable, self.root)
        self.assertTrue(config["hooks"]["PostToolUse"][0]["hooks"][0]["async"])
        with self.assertRaises(CompanionError):
            handle({"hook_event_name": "PostToolUse", "cwd": str(self.base)}, self.root, self.state, self.config)
        self.assertEqual(handle({"hook_event_name": "SessionEnd", "cwd": str(self.root)}, self.root, self.state, self.config), {})

    def test_real_hook_context_and_reused_snapshot(self):
        root, state = self.base / "hook-project", self.base / "hook-state"
        root.mkdir()
        (root / "bad.py").write_text("value = (")
        payload = {"hook_event_name": "PostToolUse", "cwd": str(root), "transcript_path": str(self.base / "never-read"), "tool_input": {"command": "never executed"}}
        first = handle(payload, root, state, self.config)
        self.assertIn("additionalContext", first["hookSpecificOutput"])
        context = json.loads(first["hookSpecificOutput"]["additionalContext"])
        self.assertFalse(context["trusted_instructions"])
        second = handle(payload, root, state, self.config)
        self.assertEqual(first, second)
        self.assertFalse((self.base / "never-read").exists())

    def test_hook_context_drops_whole_observations_without_corrupting_json(self):
        from unittest.mock import patch
        report = {"status": "failed", "snapshot_id": "fixture", "results": [{"findings": [{"finding_id": "fixture", "classification": "check_failure", "rule_id": "python.syntax", "locations": [{"path": "x" * 6000}], "freshness": "current"}]}]}
        with patch("coding_companion.cli.invoke", return_value=report):
            output = handle({"hook_event_name": "PostToolUse", "cwd": str(self.root)}, self.root, self.state, self.config)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertLessEqual(len(context), 4000)
        document = json.loads(context)
        self.assertEqual(document["observations"], [])
        self.assertIn("omitted", document["coverage"])

    def test_hook_launcher_works_without_pythonpath_or_global_installation(self):
        import subprocess
        root = self.base / "standalone-hook"
        root.mkdir()
        (root / "bad.py").write_text("broken = (")
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        executable = Path(__file__).resolve().parents[1] / "src/coding_companion/hook_entry.py"
        output = subprocess.run([sys.executable, str(executable), "hook", "--project", str(root), "--state-dir", str(self.base / "standalone-state")], input=json.dumps({"hook_event_name": "UserPromptSubmit", "cwd": str(root)}), capture_output=True, text=True, cwd=root, env=environment, timeout=20, check=True)
        document = json.loads(json.loads(output.stdout)["hookSpecificOutput"]["additionalContext"])
        self.assertTrue(document["observations"])

    @unittest.skipUnless(os.name == "nt", "Windows Job Object process lifetime fixture")
    def test_job_kills_descendant_after_parent_success(self):
        pid_file = self.base / "child-pid.txt"
        self.native_spec(f"import subprocess,sys\nfrom pathlib import Path\nchild=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\nPath({str(pid_file)!r}).write_text(str(child.pid))\n")
        result = self.engine.check(["native.fixture"])
        self.assertEqual(result["status"], "complete")
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        process = kernel.OpenProcess(0x100000, False, int(pid_file.read_text()))
        if process:
            try:
                self.assertEqual(kernel.WaitForSingleObject(process, 3000), 0, "Descendant survived successful parent exit")
            finally:
                kernel.CloseHandle(process)

    def test_withdraw_removes_owned_backup_and_flags_external_export(self):
        fid = self.seed()
        self.write("main.py", "value=1")
        lesson = self.engine.verify(fid, "private lesson")["lesson_id"]
        inside = self.state / "private-backup.sqlite"
        outside = self.base / "external-memory.json"
        self.store.backup(inside)
        self.store.export_memory(outside)
        result = withdraw(self.store, "lesson", lesson)
        self.assertFalse(inside.exists())
        self.assertTrue(outside.exists())
        self.assertEqual(result["cleanup"]["exports"][0]["state"], "external_removal_required")

    def package_proposal(self):
        root = Path(fixtures.ROOT)
        wheel = sorted((root / "dist").glob("coding_companion-*-py3-none-any.whl"))[-1]
        wheel_validate(wheel.read_bytes())
        evaluator, heldout = self.base / "independent-evaluator.py", self.base / "heldout.json"
        evaluator.write_text("# separately pinned test evaluator fixture\n")
        heldout.write_text('{"fixture":"independent heldout identity"}')
        proposal = {"kind": "code", "package_path": str(wheel), "base_package_sha256": installed_hash(), "evaluator_path": str(evaluator), "evaluator_sha256": digest(evaluator.read_bytes()), "fixtures_path": str(heldout), "fixtures_sha256": digest(heldout.read_bytes()), "distribution_rights": True, "schema_min": 1, "schema_max": 2}
        # This fixture tests external-attestation binding, not actual independent
        # product effectiveness. Candidate execution is separately tested below.
        evidence = {"independent": True, "base_package_sha256": proposal["base_package_sha256"], "package_sha256": digest(wheel.read_bytes()), "evaluator_sha256": proposal["evaluator_sha256"], "fixtures_sha256": proposal["fixtures_sha256"], "checks": [{"outcome": "passed", "executed": 1}]}
        proposal_path, evidence_path = self.base / "proposal.json", self.base / "attestation.json"
        proposal_path.write_text(canonical(proposal))
        evidence_path.write_text(canonical(evidence))
        return proposal_path, evidence_path, evaluator

    def test_package_attestation_exact_hash_and_review_gate(self):
        proposal, evidence, evaluator = self.package_proposal()
        with self.assertRaises(CompanionError):
            evaluate(self.store, proposal, evidence, False)
        evaluated = evaluate(self.store, proposal, evidence, True)
        with self.assertRaises(CompanionError):
            update(self.store, "activate", evaluated["candidate_id"], False)
        evaluator.write_text("changed")
        with self.assertRaises(CompanionError):
            update(self.store, "activate", evaluated["candidate_id"], True)

    def test_package_stage_launch_and_compatible_rollback(self):
        proposal, evidence, evaluator = self.package_proposal()
        evaluated = evaluate(self.store, proposal, evidence, True)
        activated = update(self.store, "activate", evaluated["candidate_id"], True)
        self.assertEqual(activated["phase"], "stable")
        self.assertEqual(activated["active"]["sha256"], evaluated["package_sha256"])
        launched = launch_active(self.store, ["doctor", "--json"], activated)
        self.assertEqual(launched["status"], "complete", launched)
        self.assertEqual(json.loads(launched["output"])["status"], "passed")
        rolled_back = update(self.store, "rollback")
        self.assertIsNone(rolled_back["active"]["path"])

    def test_pair_evaluation_rejects_unmatched_or_missing_overhead(self):
        trials = []
        for seed in range(3):
            result = {"accepted": True, "duration_seconds": 1, "tokens": 10, "cost_usd": 0, "false_alerts": 0, "user_interventions": 0, "fixture_hash": "fixture", "agent_settings_hash": "agent", "environment_hash": "host"}
            trials.append({"task_id": "task", "seed": seed, "fixture_hash": "fixture", "agent_settings_hash": "agent", "environment_hash": "host", "without": dict(result), "with": {**result, "includes_companion_overhead": True, "duration_seconds": 1.2}})
        self.assertEqual(paired({"trials": trials})["trials"], 3)
        trials[0]["with"]["fixture_hash"] = "other"
        with self.assertRaises(CompanionError):
            paired({"trials": trials})

    def test_real_unittest_adapter_nonzero_tests(self):
        import sys
        from coding_companion.native import approve
        self.write("app.py", "VALUE=2")
        self.write("tests/test_fixture.py", "import unittest,app\nclass Fixture(unittest.TestCase):\n    def test_value(self): self.assertEqual(app.VALUE,2)\n")
        self.engine.snapshot()
        script = Path(fixtures.ROOT) / "src/coding_companion/junit_probe.py"
        spec = {"check_id": "native.unittest", "argv": [sys.executable, str(script), "--report", "{artifact_dir}/tests.xml"], "inputs": ["*.py"], "parser": "junit", "report": "tests.xml", "category": "tests"}
        approve(self.store, spec)
        checked = self.engine.check(["native.unittest"])
        self.assertEqual(checked["status"], "complete", checked)
        self.assertEqual(checked["results"][0]["counts"]["executed"], 1)

    def test_external_command_file_trust_cannot_drift(self):
        import sys
        from coding_companion.native import approve
        self.write("input.txt", "fixture")
        script = self.base / "outside-probe.py"
        script.write_text("print('first')")
        self.engine.snapshot()
        spec = {"check_id": "native.external", "argv": [sys.executable, str(script)], "inputs": ["input.txt"], "parser": "exit_code", "report": None, "category": "build"}
        approve(self.store, spec)
        script.write_text("print('changed')")
        self.assertEqual(self.engine.check(["native.external"])["results"][0]["outcome"], "blocked")

    def test_sarif_native_report_is_operational(self):
        from coding_companion.native import approve
        import sys
        body = canonical({"version": "2.1.0", "runs": [{"results": [{"ruleId": "fixture-rule", "message": {"text": "fixture finding"}}]}]})
        self.write("probe.py", f"import sys\nfrom pathlib import Path\nPath(sys.argv[1], 'report.sarif').write_text({body!r})\n")
        self.engine.snapshot()
        spec = {"check_id": "native.sarif", "argv": [sys.executable, "probe.py", "{artifact_dir}"], "inputs": ["probe.py"], "parser": "sarif", "report": "report.sarif", "category": "security"}
        approve(self.store, spec)
        result = self.engine.check(["native.sarif"])
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["results"][0]["findings"][0]["evidence"])

    def test_native_snapshot_binds_external_input_and_stays_current(self):
        self.native_spec("raise SystemExit(1)")
        report = self.engine.check(["native.fixture"])
        sid = report["snapshot_id"]
        stored = json.loads(self.store.db.execute("SELECT coverage_json FROM snapshots WHERE snapshot_id=?", (sid,)).fetchone()[0])
        self.assertIn("command_files", stored["provenance"]["native_inputs"]["native.fixture"])
        self.engine.refresh_findings()
        fid = report["results"][0]["findings"][0]["finding_id"]
        self.assertEqual(self.store.inspect(fid)["observation"]["freshness"], "current")

    def test_withdraw_scrubs_durable_memory_reply(self):
        from coding_companion.cli import Dispatcher
        from coding_companion.mailbox import Mailbox, response_body
        from coding_companion.common import atomic_write, identifier
        fid = self.seed()
        self.write("main.py", "value=1")
        lesson = self.engine.verify(fid, "PRIVATE_LESSON_PHRASE")["lesson_id"]
        mailbox = Mailbox(self.store, Dispatcher(self.engine))
        request = {"schema_version": "1.0", "request_id": identifier(), "project_id": self.store.project_id, "operation": "memory_search", "args": {"query": "PRIVATE_LESSON_PHRASE"}, "created_at": now(), "deadline_at": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat().replace("+00:00", "Z")}
        atomic_write(self.state / "inbox" / f"{request['request_id']}.json", canonical(request).encode())
        mailbox.drain()
        reply_file = self.state / "responses" / f"{request['request_id']}.json"
        old = json.loads(reply_file.read_text())
        self.assertIn("PRIVATE_LESSON_PHRASE", canonical(old))
        withdraw(self.store, "lesson", lesson)
        self.assertIsNone(response_body(old, self.state))
        history = self.store.db.execute("SELECT payload_json,result_json FROM events WHERE request_id=?", (request["request_id"],)).fetchone()
        self.assertNotIn("PRIVATE_LESSON_PHRASE", canonical(dict(history)))
        mailbox.drain()
        self.assertNotIn("PRIVATE_LESSON_PHRASE", reply_file.read_text())

    def test_weakened_captured_threshold_cannot_verify_repair(self):
        data = {"captured_revision": "fixture", "workload": {"duration_seconds": 10, "concurrency": 2}, "latency_ms": [100], "errors": 0, "thresholds": {"p95_ms": 50}}
        failed = self.manifest_check("performance.contracts", "companion.metrics.json", data, "failed")
        fid = failed["results"][0]["findings"][0]["finding_id"]
        data["thresholds"]["p95_ms"] = 200
        self.write("companion.metrics.json", canonical(data))
        verified = self.engine.verify(fid)
        self.assertEqual(verified["resolution"], "unresolved")
        self.assertIn("verification_blocker", verified)

    def test_skipping_original_failing_test_cannot_verify(self):
        from coding_companion.native import approve
        import sys
        failed_xml = '<testsuite tests="1"><testcase name="regression"><failure/></testcase></testsuite>'
        script = f"import sys\nfrom pathlib import Path\nPath(sys.argv[1],'tests.xml').write_text({failed_xml!r})"
        self.write("probe.py", script)
        self.engine.snapshot()
        spec = {"check_id": "native.identity", "argv": [sys.executable, "probe.py", "{artifact_dir}"], "inputs": ["probe.py"], "parser": "junit", "report": "tests.xml", "category": "tests"}
        approve(self.store, spec)
        report = self.engine.check(["native.identity"])
        fid = report["results"][0]["findings"][0]["finding_id"]
        skipped_xml = '<testsuite tests="2"><testcase name="regression"><skipped/></testcase><testcase name="other"/></testsuite>'
        self.write("probe.py", f"import sys\nfrom pathlib import Path\nPath(sys.argv[1],'tests.xml').write_text({skipped_xml!r})")
        self.engine.snapshot()
        approve(self.store, spec)
        verified = self.engine.verify(fid)
        self.assertEqual(verified["resolution"], "unresolved")
        self.assertIn("verification_blocker", verified)

    def test_readonly_sqlite_probe_real_foreign_key_repair(self):
        import sqlite3, sys
        from contextlib import closing
        from coding_companion.native import approve
        database = self.root / "customer.sqlite"
        with closing(sqlite3.connect(database)) as db:
            db.executescript("CREATE TABLE parent(id INTEGER PRIMARY KEY); CREATE TABLE child(parent_id INTEGER REFERENCES parent(id)); INSERT INTO child VALUES(1);")
            db.commit()
        self.write("database-contract.json", '{"queries":[{"id":"row-count","sql":"SELECT count(*) FROM child","equals":1}]}')
        self.engine.snapshot()
        spec = {"check_id": "native.database", "argv": [sys.executable, str(Path(fixtures.ROOT) / "src/coding_companion/sqlite_probe.py"), "--database", "customer.sqlite", "--contract", "database-contract.json", "--report", "{artifact_dir}/tests.xml"], "inputs": ["database-contract.json"], "parser": "junit", "report": "tests.xml", "category": "tests"}
        approve(self.store, spec)
        before = digest(database.read_bytes())
        failed = self.engine.check(["native.database"])
        self.assertEqual(failed["status"], "failed", failed)
        self.assertEqual(before, digest(database.read_bytes()), "Probe mutated customer data")
        fid = failed["results"][0]["findings"][0]["finding_id"]
        with closing(sqlite3.connect(database)) as db:
            db.execute("INSERT INTO parent VALUES(1)")
            db.commit()
        self.engine.snapshot()
        approve(self.store, spec)
        self.assertEqual(self.engine.verify(fid)["resolution"], "verified_resolved")

    def test_loopback_http_probe_real_contract(self):
        import http.server, sys
        from coding_companion.native import approve
        class Fixture(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                body = b'{"status":"ready"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.write("api-contract.json", canonical({"base_url": f"http://127.0.0.1:{server.server_port}", "requests": [{"id": "readiness", "path": "/", "expected": {"status": 200, "content_type": "application/json", "json_fields": {"status": "ready"}}}]}))
            self.engine.snapshot()
            spec = {"check_id": "native.http", "argv": [sys.executable, str(Path(fixtures.ROOT) / "src/coding_companion/api_probe.py"), "--contract", "api-contract.json", "--report", "{artifact_dir}/tests.xml"], "inputs": ["api-contract.json"], "parser": "junit", "report": "tests.xml", "category": "tests"}
            approve(self.store, spec)
            checked = self.engine.check(["native.http"])
            self.assertEqual(checked["status"], "complete", checked)
            self.assertEqual(checked["results"][0]["counts"]["executed"], 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_nonfinite_json_and_resource_settings_rejected(self):
        from coding_companion.config import load_config
        self.write("invalid.json", '{"value":NaN}')
        self.assertEqual(self.engine.check(["structured.formats"])["status"], "failed")
        path = self.base / "invalid.toml"
        path.write_text("[resources]\npoll_seconds=inf")
        with self.assertRaises(CompanionError):
            load_config(path)


if __name__ == "__main__":
    unittest.main()
