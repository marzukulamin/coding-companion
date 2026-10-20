"""Real browser regression cases for focus restoration and overlay hit testing."""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import site
import sys
import tempfile
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def validate(dependencies, executable):
    site.addsitedir(str(dependencies.resolve()))
    from coding_companion.browser_probe import run
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        page = root / "index.html"
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(root)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            contract = {"base_url": f"http://127.0.0.1:{server.server_port}", "paths": ["/index.html"], "viewports": [{"width": 640, "height": 480}], "checks": [{"kind": "selector_receives_pointer", "selector": "#go"}]}
            results = []
            for overlay, expected in (("auto", 1), ("none", 0)):
                page.write_text(f'<button id="go">Go</button><div style="position:fixed;inset:0;pointer-events:{overlay}"></div>', encoding="utf-8")
                report = root / f"overlay-{overlay}.xml"
                assert run(contract, report, str(executable)) == expected
                suite = ET.parse(report).getroot()
                assert suite.get("errors") == "0" and suite.get("tests") == "1"
                results.append({"case": f"overlay-{overlay}", "expected_failure": bool(expected)})
            for restore, expected in ((False, 1), (True, 0)):
                page.write_text('''<button id="go" onclick="modal.showModal();close.focus()">Open</button>
                    <dialog id="modal"><button id="close" onclick="modal.close();'''
                    + ('go.focus()' if restore else 'other.focus()')
                    + '''">Close</button></dialog><button id="other">Other</button>''', encoding="utf-8")
                contract["actions"] = [{"kind": "click", "selector": "#go"}, {"kind": "click", "selector": "#close"}]
                contract["checks"] = [{"kind": "selector_focused", "selector": "#go"}]
                report = root / f"focus-{restore}.xml"
                assert run(contract, report, str(executable)) == expected
                assert ET.parse(report).getroot().get("errors") == "0"
                results.append({"case": f"focus-restoration-{restore}", "expected_failure": bool(expected)})
            page.write_text('<button id="go">Go</button><button id="other">Other</button>', encoding="utf-8")
            contract["actions"] = [{"kind": "focus", "selector": "#go"}, {"kind": "press", "selector": "#go", "key": "Tab"}]
            contract["checks"] = [{"kind": "selector_focused", "selector": "#other"}]
            assert run(contract, root / "keyboard.xml", str(executable)) == 0
            results.append({"case": "keyboard-tab", "expected_failure": False})
            return {"status": "passed", "cases": results, "scope": "Local explicit focus and center-point hit tests; not full accessibility certification"}
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
