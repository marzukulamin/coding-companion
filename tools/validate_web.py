"""Exercise real installed web tools on an explicitly named, owned synthetic fixture.

Install fixture dependencies separately with npm --ignore-scripts. This validator
never installs packages or uses a customer project as its fixture.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coding_companion.common import canonical
from coding_companion.config import Config
from coding_companion.discovery import discover
from coding_companion.engine import Engine
from coding_companion.native import approve
from coding_companion.ownership import Ownership
from coding_companion.storage import Store


def validate(project: Path) -> dict:
    project = project.resolve()
    manifest = json.loads((project / "package.json").read_text(encoding="utf-8"))
    if manifest.get("name") != "companion-web-certification-fixture" or manifest.get("private") is not True:
        raise ValueError("An explicitly named private companion-web-certification-fixture is required")
    marker = project / ".companion" / "validator-owned.json"
    owned = ["tsconfig.json", "eslint.config.mjs", "index.html", "src/logic.ts", "src/logic.test.ts", "src/main.ts", "src/lint.js"]
    if not marker.exists() and any((project / name).exists() for name in owned):
        raise ValueError("Refusing to replace pre-existing files in an unmarked fixture")
    if marker.exists() and json.loads(marker.read_text(encoding="utf-8")) != {"fixture": "web-v1", "files": owned}:
        raise ValueError("Unexpected fixture ownership marker")
    marker.parent.mkdir(exist_ok=True)
    marker.write_text(canonical({"fixture": "web-v1", "files": owned}), encoding="utf-8")

    def write(name, content):
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    write("tsconfig.json", canonical({"compilerOptions": {"target": "ES2022", "module": "ESNext", "moduleResolution": "Bundler", "strict": True, "skipLibCheck": True, "noEmit": True}, "include": ["src"]}))
    write("eslint.config.mjs", "export default [{files:['src/**/*.js'], rules:{'no-debugger':'error'}}];\n")
    write("index.html", '<!doctype html><html><body><main id="app"></main><script type="module" src="/src/main.ts"></script></body></html>\n')
    write("src/logic.ts", "export const VALUE: number = 1;\n")
    test = "import {expect, test} from 'vitest';\nimport {VALUE} from './logic';\ntest('original regression', () => expect(VALUE).toBe(2));\n"
    write("src/logic.test.ts", test)
    write("src/main.ts", "import {VALUE} from './logic';\ndocument.getElementById('app')!.textContent = String(VALUE);\n")
    write("src/lint.js", "export const healthy = true;\n")
    config = Config(timeout_seconds=60)
    state = project / ".companion" / "state"
    with Ownership(state):
        store = Store(project, state, config)
        try:
            engine = Engine(store)
            inventory = discover(project, config, state)
            items = [p for p in inventory["native_proposals"] if p["adapter"].startswith("web.")]
            if len(items) != 4 or any(not p["available"] for p in items):
                raise AssertionError({"missing_tools": items})
            specs = {item["check_id"]: item["spec"] for item in items}

            def renew():
                engine.snapshot()
                for spec in specs.values():
                    approve(store, spec)

            def require(report, expected):
                outcomes = {r["check_id"]: r["outcome"] for r in report["results"]}
                if outcomes != expected:
                    raise AssertionError(report)
                return {r["check_id"]: r for r in report["results"]}

            renew()
            baseline = require(engine.check(list(specs)), {"native.web.typecheck": "passed", "native.web.lint": "passed", "native.web.build": "passed", "native.web.tests": "failed"})
            test_id = baseline["native.web.tests"]["findings"][0]["finding_id"]
            assert baseline["native.web.tests"]["counts"]["executed"] == 1
            write("src/logic.ts", "export const VALUE: number = 2;\n")
            renew()
            assert engine.verify(test_id)["resolution"] == "verified_resolved"

            write("src/logic.ts", "export const VALUE: number = 'invalid';\n")
            write("src/lint.js", "debugger;\nexport const healthy = true;\n")
            renew()
            seeded = require(engine.check(["native.web.typecheck", "native.web.lint"]), {"native.web.typecheck": "failed", "native.web.lint": "failed"})
            write("src/logic.ts", "export const VALUE: number = 2;\n")
            write("src/lint.js", "export const healthy = true;\n")
            renew()
            for result in seeded.values():
                assert engine.verify(result["findings"][0]["finding_id"])["resolution"] == "verified_resolved"

            write("src/logic.ts", "export const VALUE: number = 1;\n")
            renew()
            recurrence = require(engine.check(["native.web.tests"]), {"native.web.tests": "failed"})
            original_id = recurrence["native.web.tests"]["findings"][0]["finding_id"]
            write("src/logic.test.ts", test.replace("toBe(2)", "toBe(1)"))
            renew()
            weakened = engine.verify(original_id)
            assert weakened["results"][0]["outcome"] == "passed"
            assert weakened["resolution"] == "unresolved" and "verification_blocker" in weakened
            write("src/logic.test.ts", test)
            write("src/logic.ts", "export const VALUE: number = 2;\n")
            renew()
            assert engine.verify(original_id)["resolution"] == "verified_resolved"
            require(engine.check(list(specs)), dict.fromkeys(specs, "passed"))
            store.check_integrity()
            return {"status": "passed", "project": str(project), "tool_versions": {p["adapter"]: p["tool_version"] for p in items}, "native_checks": len(specs), "junit_cases": 1, "seeded_test_type_and_lint_failures": True, "current_repairs_verified": True, "weakened_test_rejected": True, "custom_scripts_executed": False}
        finally:
            store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.project), indent=2))
