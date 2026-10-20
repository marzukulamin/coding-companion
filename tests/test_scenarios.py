from __future__ import annotations

import http.server
import json
import tempfile
import threading
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from coding_companion.scenario_probe import batches, run
import test_runtime as fixtures
from coding_companion.native import approve


class ScenarioNativeTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    tearDown = fixtures.RuntimeTests.tearDown
    write = fixtures.RuntimeTests.write

    def test_native_matrix_current_repair_and_weakened_contract_rejection(self):
        self.write("policy.json", '{"leak":true}')
        policy = self.root / "policy.json"
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                permitted = self.headers.get("X-Actor") == "alice"
                leak = json.loads(policy.read_text())["leak"]
                self.send_response(200 if permitted or leak else 403)
                self.end_headers()
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            contract = {"base_url": f"http://127.0.0.1:{server.server_port}", "access_matrix": {
                "actors": {"alice": {"X-Actor": "alice"}, "bob": {"X-Actor": "bob"}},
                "resources": [{"path": "/tenant/alice", "expected_by_actor": {"alice": {"status": 200}, "bob": {"status": 403}}}],
            }}
            self.write("scenarios.json", json.dumps(contract))
            spec = {"check_id": "native.scenarios", "argv": [sys.executable, str(Path(__file__).resolve().parents[1] / "src/coding_companion/scenario_probe.py"), "--contract", "scenarios.json", "--report", "{artifact_dir}/tests.xml"], "inputs": ["*"], "parser": "junit", "report": "tests.xml", "category": "tests"}
            self.engine.snapshot()
            approve(self.store, spec)
            seeded = self.engine.check(["native.scenarios"])
            self.assertEqual(seeded["status"], "failed")
            finding = seeded["results"][0]["findings"][0]["finding_id"]
            contract["access_matrix"]["resources"][0]["expected_by_actor"]["bob"]["status"] = 200
            self.write("scenarios.json", json.dumps(contract))
            self.engine.snapshot()
            approve(self.store, spec)
            self.assertEqual(self.engine.verify(finding)["resolution"], "unresolved")
            contract["access_matrix"]["resources"][0]["expected_by_actor"]["bob"]["status"] = 403
            self.write("scenarios.json", json.dumps(contract))
            self.write("policy.json", '{"leak":false}')
            self.engine.snapshot()
            approve(self.store, spec)
            self.assertEqual(self.engine.verify(finding)["resolution"], "verified_resolved")
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


class ScenarioTests(unittest.TestCase):
    def test_incomplete_actor_matrix_and_request_budgets_fail_before_execution(self):
        invalid = [
            {"access_matrix": {"actors": {"alice": {}, "bob": {}}, "resources": [{"path": "/a", "expected_by_actor": {"alice": {"status": 200}}}]}},
            {"steps": [{"parallel": [{"path": "/", "expected": {"status": 200}}] * 17}]},
            {"steps": [{"path": "/", "expected": {"status": 200}}] * 101},
            {"steps": [{"path": "/"}]},
        ]
        for contract in invalid:
            with self.assertRaises(ValueError):
                batches(contract)
        with tempfile.TemporaryDirectory() as directory, patch("coding_companion.scenario_probe.request_probe") as probe:
            with self.assertRaises(ValueError):
                run({"steps": [{"method": "POST", "path": "/", "expected": {"status": 200}}]}, Path(directory) / "tests.xml")
            probe.assert_not_called()

    def test_real_tenant_matrix_detects_leak_and_clean_denial(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            leak = True
            def log_message(self, *args):
                pass
            def do_GET(self):
                permitted = self.headers.get("X-Actor") == self.path.removeprefix("/tenant/")
                self.send_response(200 if permitted or self.leak else 403)
                self.end_headers()
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            contract = {"base_url": f"http://127.0.0.1:{server.server_port}", "access_matrix": {
                "actors": {"alice": {"X-Actor": "alice"}, "bob": {"X-Actor": "bob"}, "anonymous": {}},
                "resources": [{"path": f"/tenant/{owner}", "expected_by_actor": {actor: {"status": 200 if actor == owner else 403} for actor in ("alice", "bob", "anonymous")}} for owner in ("alice", "bob")],
            }}
            with tempfile.TemporaryDirectory() as directory:
                report = Path(directory) / "tests.xml"
                self.assertEqual(run(contract, report), 1)
                self.assertEqual(ET.parse(report).getroot().get("failures"), "4")
                Handler.leak = False
                self.assertEqual(run(contract, report), 0)
                self.assertEqual(ET.parse(report).getroot().get("tests"), "6")
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_concurrent_lost_update_and_post_batch_invariant(self):
        barrier, mutex = threading.Barrier(2), threading.Lock()
        class Handler(http.server.BaseHTTPRequestHandler):
            count, broken = 0, True
            def log_message(self, *args):
                pass
            def do_POST(self):
                if self.broken:
                    before = Handler.count
                    barrier.wait(timeout=3)
                    Handler.count = before + 1
                else:
                    with mutex:
                        Handler.count += 1
                self.send_response(200)
                self.end_headers()
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"count": Handler.count}).encode())
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            contract = {"base_url": f"http://127.0.0.1:{server.server_port}", "steps": [
                {"parallel": [{"method": "POST", "path": "/increment", "expected": {"status": 200}} for _ in range(2)]},
                {"path": "/state", "expected": {"status": 200, "json_fields": {"count": 2}}},
            ]}
            with tempfile.TemporaryDirectory() as directory:
                report = Path(directory) / "tests.xml"
                self.assertEqual(run(contract, report, allow_mutation=True), 1)
                suite = ET.parse(report).getroot()
                self.assertEqual((suite.get("tests"), suite.get("failures"), suite.get("errors")), ("3", "1", "0"))
                Handler.broken, Handler.count = False, 0
                self.assertEqual(run(contract, report, allow_mutation=True), 0)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_external_origin_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                run({"base_url": "https://example.com", "steps": [{"path": "/", "expected": {"status": 200}}]}, Path(directory) / "tests.xml")
