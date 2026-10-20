"""Real local browser fixture acceptance; does not contact a hosted app."""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def validate(dependencies: Path, executable: Path):
    from coding_companion.config import Config
    from coding_companion.engine import Engine
    from coding_companion.native import approve
    from coding_companion.ownership import Ownership
    from coding_companion.storage import Store
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary).resolve()
        project, state = base / "project", base / "state"
        project.mkdir()
        page = project / "index.html"
        page.write_text('<!doctype html><html><body><button id="go">Go</button><script>console.error("fixture error")</script></body></html>')
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(project)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            contract = {"base_url": f"http://127.0.0.1:{server.server_port}", "paths": ["/index.html"], "viewports": [{"width": 640, "height": 480}], "checks": [{"kind": "no_console_errors"}, {"kind": "no_root_overflow"}, {"kind": "selector_focusable", "selector": "#go"}]}
            (project / "browser.json").write_text(json.dumps(contract))
            with Ownership(state):
                store = Store(project, state, Config(timeout_seconds=60))
                try:
                    engine = Engine(store)
                    engine.snapshot()
                    spec = {"check_id": "native.browser", "argv": [sys.executable, str(ROOT / "src/coding_companion/browser_probe.py"), "--contract", "browser.json", "--report", "{artifact_dir}/tests.xml", "--executable", str(executable.resolve()), "--dependency-dir", str(dependencies.resolve())], "inputs": ["*"], "parser": "junit", "report": "tests.xml", "category": "tests"}
                    approve(store, spec)
                    seeded = engine.check(["native.browser"])
                    assert seeded["status"] == "failed", seeded
                    assert seeded["results"][0]["counts"]["executed"] == 3, seeded
                    finding = seeded["results"][0]["findings"][0]["finding_id"]
                    page.write_text('<!doctype html><html><body><button id="go">Go</button></body></html>')
                    engine.snapshot()
                    approve(store, spec)
                    clean = engine.verify(finding)
                    assert clean["resolution"] == "verified_resolved", clean
                    return {"status": "passed", "browser": "existing_headless_chrome", "cases_per_run": 3, "seeded_console_failure": True, "current_repair_verified": True, "network_scope": "loopback_fixture"}
                finally:
                    store.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dependencies", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.dependencies, args.executable), indent=2))
