from __future__ import annotations

import unittest
import contextlib
import io
import json
from dataclasses import replace
from unittest.mock import patch

import test_runtime as fixtures
from coding_companion.cli import main
from coding_companion.common import canonical
from coding_companion.discovery import discover, snapshot
from coding_companion.impact import affected, impact_graph
from coding_companion.native import approve, module_versions, test_contract_hashes, validate_spec
from coding_companion.engine import Engine
from coding_companion.storage import Store


class WebTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    tearDown = fixtures.RuntimeTests.tearDown
    write = fixtures.RuntimeTests.write
    native_spec = fixtures.RuntimeTests.native_spec

    def test_side_effect_reexport_and_literal_dynamic_import_closure(self):
        self.write("src/setup.mjs", "export const value = 1;")
        self.write("src/barrel.mjs", "export * from './setup.mjs';")
        self.write("src/app.mjs", "import './barrel.mjs';")
        self.write("src/lazy.mjs", "const module = import('./setup.mjs');")
        self.write("unrelated.mjs", "export const value = 2;")
        route = affected(self.engine.snapshot(), ["src/setup.mjs"])
        self.assertEqual(route["scope"], "changed")
        self.assertEqual(route["paths"], ["src/app.mjs", "src/barrel.mjs", "src/lazy.mjs", "src/setup.mjs"])

    def test_typescript_emitted_names_and_directory_indexes(self):
        self.write("src/helper.ts", "export const value = 1;")
        self.write("src/widget/index.jsx", "export const value = 2;")
        self.write("src/app.tsx", "import { value } from './helper.js';\nimport './widget';")
        graph = impact_graph(self.engine.snapshot())
        self.assertEqual(graph["edges"]["src/app.tsx"], ["src/helper.ts", "src/widget/index.jsx"])
        self.assertEqual(graph["unresolved"], [])

    def test_typescript_alias_inheritance_jsonc_and_specificity(self):
        self.write("tsconfig.base.json", '{"compilerOptions":{"baseUrl":".","paths":{"@/*":["src/*"],"@/special/*":["special/*"]}}}')
        self.write("tsconfig.json", '{// local config\n"extends":"./tsconfig.base",}')
        self.write("src/helper.ts", "export const value = 1;")
        self.write("special/value.ts", "export const value = 2;")
        self.write("src/app.ts", "import '@/helper'; import '@/special/value';")
        graph = impact_graph(self.engine.snapshot())
        self.assertEqual(graph["edges"]["src/app.ts"], ["special/value.ts", "src/helper.ts"])
        self.assertEqual(affected(self.engine.snapshot(), ["src/helper.ts"])["scope"], "changed")

    def test_child_paths_without_baseurl_use_child_directory(self):
        self.write("tsconfig.json", '{"compilerOptions":{}}')
        self.write("app/tsconfig.json", '{"extends":"../tsconfig.json","compilerOptions":{"paths":{"@/*":["src/*"]}}}')
        self.write("app/src/helper.ts", "export const value = 1;")
        self.write("app/src/main.ts", "import '@/helper';")
        self.assertEqual(impact_graph(self.engine.snapshot())["edges"]["app/src/main.ts"], ["app/src/helper.ts"])

    def test_workspace_exports_and_emitted_typescript_closure(self):
        self.write("packages/lib/package.json", '{"name":"@local/lib","exports":{".":"./src/index.js","./utils/*":"./src/utils/*.js"}}')
        self.write("packages/lib/src/index.ts", "export const value = 1;")
        self.write("packages/lib/src/utils/math.ts", "export const value = 2;")
        self.write("app.ts", "import '@local/lib'; import '@local/lib/utils/math';")
        graph = impact_graph(self.engine.snapshot())
        self.assertEqual(graph["edges"]["app.ts"], ["packages/lib/src/index.ts", "packages/lib/src/utils/math.ts"])
        self.assertEqual(graph["unresolved"], [])

    def test_conditional_duplicate_and_escaping_exports_stay_unresolved(self):
        self.write("app.ts", "import '@local/lib';")
        for exports in ({"import": "./src/index.ts", "require": "./src/other.ts"}, "../outside.ts"):
            self.write("lib/package.json", json.dumps({"name": "@local/lib", "exports": exports}))
            self.assertEqual(impact_graph(self.engine.snapshot())["unresolved"], ["app.ts"])
        self.write("lib/package.json", '{"name":"@local/lib","main":"index.ts"}')
        self.write("lib/index.ts", "export const value = 1;")
        self.write("other/package.json", '{"name":"@local/lib","main":"index.ts"}')
        self.assertEqual(impact_graph(self.engine.snapshot())["unresolved"], ["app.ts"])

    def test_cyclic_missing_and_external_tsconfig_inheritance_fallback(self):
        self.write("app.ts", "import '@/helper';")
        self.write("helper.ts", "export const value = 1;")
        for parent in ("./tsconfig.json", "./missing.json", "external-config"):
            self.write("tsconfig.json", json.dumps({"extends": parent, "compilerOptions": {"paths": {"@/*": ["*"]}}}))
            self.assertEqual(affected(self.engine.snapshot(), ["helper.ts"])["scope"], "project")

    def test_overridden_inherited_alias_base_and_bundler_entries_fallback(self):
        self.write("tsconfig.json", '{"compilerOptions":{"baseUrl":".","paths":{"@/*":["src/*"]}}}')
        self.write("app/tsconfig.json", '{"extends":"../tsconfig.json","compilerOptions":{"baseUrl":"."}}')
        self.write("app/main.ts", "import '@/helper';")
        self.write("src/helper.ts", "export const value = 1;")
        self.assertEqual(affected(self.engine.snapshot(), ["src/helper.ts"])["scope"], "project")
        self.write("app/main.ts", "import '@local/lib';")
        self.write("lib/package.json", '{"name":"@local/lib","main":"index.ts","module":"module.ts"}')
        self.write("lib/index.ts", "export const value = 1;")
        self.assertIn("app/main.ts", impact_graph(self.engine.snapshot())["unresolved"])

    def test_computed_alias_and_external_paths_force_project_scope(self):
        self.write("helper.ts", "export const value = 1;")
        for code in ("import(name)", "require(name)", "import x from '@/helper'", "import '../../outside.js'", "import.meta.glob('./*.ts')", "require.resolve('./helper')"):
            with self.subTest(code=code):
                self.write("app.ts", code)
                self.assertEqual(affected(self.engine.snapshot(), ["helper.ts"])["scope"], "project")

    def test_config_and_unknown_assets_force_project_scope(self):
        self.write("app.ts", "export const value = 1;")
        for path in ("tsconfig.app.json", "apps/web/vite.config.ts", "style.css", "index.html"):
            self.write(path, "{}")
            self.assertEqual(affected(self.engine.snapshot(), [path])["scope"], "project", path)

    def test_absolute_python_from_import_and_initializer_closure(self):
        self.write("pkg/__init__.py", "value = 1")
        self.write("pkg/helper.py", "value = 2")
        self.write("consumer.py", "from pkg import helper")
        self.write("direct.py", "import pkg.helper")
        self.write("unrelated.py", "value = 3")
        snap = self.engine.snapshot()
        self.assertEqual(affected(snap, ["pkg/helper.py"])["paths"], ["consumer.py", "direct.py", "pkg/helper.py"])
        self.assertIn("consumer.py", affected(snap, ["pkg/__init__.py"])["paths"])

    def install_fixture(self, directory="", tools=("typescript", "eslint", "vite", "vitest")):
        prefix = directory + "/" if directory else ""
        self.write(prefix + "package.json", canonical({"name": "fixture", "devDependencies": {name: "1.0.0" for name in tools}}))
        self.write(prefix + "tsconfig.json", "{}")
        self.write(prefix + "eslint.config.mjs", "export default [];")
        for name in tools:
            binary = "tsc" if name == "typescript" else name
            self.write(f"node_modules/{name}/package.json", canonical({"name": name, "version": "1.0.0", "bin": {binary: "bin/cli.mjs"}}))
            self.write(f"node_modules/{name}/bin/cli.mjs", "export {};")

    def test_reviewable_installed_web_specs_without_execution(self):
        self.install_fixture()
        with patch("coding_companion.web_adapters.shutil.which", return_value="node"):
            proposals = discover(self.root, self.config)["native_proposals"]
        items = [p for p in proposals if p["adapter"].startswith("web.")]
        self.assertEqual(len(items), 4)
        for item in items:
            validate_spec(item["spec"])
            self.assertEqual(item["trust"], "unreviewed")
            self.assertTrue(item["available"])
            self.assertNotIn("npx", item["spec"]["argv"])
        self.assertEqual(next(p for p in items if p["adapter"] == "web.vitest")["spec"]["parser"], "junit")

    def test_missing_tools_and_config_are_visible_blocks(self):
        self.write("package.json", '{"devDependencies":{"typescript":"1","vitest":"1"}}')
        proposals = discover(self.root, self.config)["native_proposals"]
        items = [p for p in proposals if p["adapter"].startswith("web.")]
        self.assertEqual(len(items), 2)
        self.assertTrue(all(not p["available"] and p["spec"] is None and p["blocked_reasons"] for p in items))

    def test_cli_exports_reviewable_spec_without_approving_or_overwriting(self):
        self.install_fixture()
        output = self.base / "review.json"
        args = ["probe", "propose", "native.web.tests", "--project", str(self.root), "--state-dir", str(self.base / "export-state"), "--output", str(output), "--json"]
        with patch("coding_companion.web_adapters.shutil.which", return_value="node"), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 0)
            self.assertEqual(main(args), 2)
        validate_spec(json.loads(output.read_text(encoding="utf-8")))
        self.assertFalse(list((self.base / "export-state").rglob("trusted-probes.json")))

    def test_monorepo_package_hoisted_tools_have_distinct_ids(self):
        self.install_fixture("apps/one")
        self.install_fixture("apps/two")
        with patch("coding_companion.web_adapters.shutil.which", return_value="node"):
            items = [p for p in discover(self.root, self.config)["native_proposals"] if p["adapter"].startswith("web.")]
        self.assertEqual(len(items), 8)
        self.assertEqual(len({p["check_id"] for p in items}), 8)
        self.assertTrue(all(p["available"] for p in items))
        self.assertTrue(all(p["package"] in {"apps/one", "apps/two"} for p in items))

    def test_invalid_manifest_shapes_do_not_crash_discovery(self):
        for data in ({"scripts": []}, {"dependencies": "react"}, {"scripts": {"test": 1}}, []):
            with self.subTest(data=data):
                self.write("package.json", canonical(data))
                inventory = discover(self.root, self.config)
                self.assertFalse(inventory["packages"][0]["parsed"])
                self.assertIn("error", inventory["packages"][0])

    def test_installed_cli_cannot_escape_its_package(self):
        self.install_fixture(tools=("vitest",))
        self.write("node_modules/vitest/package.json", '{"name":"vitest","version":"1","bin":"../../evil.mjs"}')
        item = next(p for p in discover(self.root, self.config)["native_proposals"] if p["adapter"] == "web.vitest")
        self.assertFalse(item["available"])

    def test_typescript_extensionless_bin_is_a_usable_proposal(self):
        self.install_fixture(tools=("typescript",))
        self.write("node_modules/typescript/package.json", '{"name":"typescript","version":"1","bin":{"tsc":"bin/tsc"}}')
        self.write("node_modules/typescript/bin/tsc", "#!/usr/bin/env node\nrequire('../lib/tsc.js');")
        with patch("coding_companion.web_adapters.shutil.which", return_value="node"):
            item = next(p for p in discover(self.root, self.config)["native_proposals"] if p["adapter"] == "web.typescript")
        self.assertTrue(item["available"])
        self.assertIn("--incremental", item["spec"]["argv"])

    def test_node_tool_internal_code_changes_provenance(self):
        self.install_fixture(tools=("typescript",))
        spec = {"argv": ["node", str(self.root / "node_modules/typescript/bin/cli.mjs")]}
        initial = module_versions(spec)
        self.write("node_modules/typescript/lib/compiler.js", "module.exports = 1;")
        self.assertNotEqual(initial, module_versions(spec))

    def test_restored_snapshot_is_current_and_survives_reopening(self):
        self.write("library.py", "value = 1")
        self.write("other.py", "value = 1")
        original = self.engine.snapshot()
        created = self.store.db.execute("SELECT created_at FROM snapshots WHERE snapshot_id=?", (original.snapshot_id,)).fetchone()[0]
        self.write("library.py", "value = 2")
        self.engine.snapshot()
        self.write("library.py", "value = 1")
        restored = self.engine.snapshot()
        self.assertEqual(restored.snapshot_id, original.snapshot_id)
        self.assertEqual(self.store.latest_snapshot_id(), original.snapshot_id)
        self.assertEqual(self.store.db.execute("SELECT state,created_at FROM snapshots WHERE snapshot_id=?", (original.snapshot_id,)).fetchone()[:], ("current", created))
        self.store.close()
        self.store = Store(self.root, self.state, self.config)
        self.engine = Engine(self.store)
        self.assertEqual(self.store.latest_snapshot_id(), original.snapshot_id)
        self.write("other.py", "value = 2")
        report = self.engine.check(["python.syntax"], scope="changed")
        self.assertEqual(report["changed_paths"], ["other.py"])
        self.assertEqual(report["results"][0]["counts"]["executed"], 1)

    def test_native_approval_hashes_fresh_inputs_after_restore(self):
        self.write("app.py", "value = 1")
        spec = self.native_spec("print('fixture')")["spec"]
        spec["inputs"] = ["*"]
        approve(self.store, spec)
        self.assertEqual(self.engine.check(["native.fixture"])["status"], "complete")
        self.write("app.py", "value = 2")
        approve(self.store, spec)
        self.assertEqual(self.engine.check(["native.fixture"])["status"], "complete")
        self.write("app.py", "value = 1")
        approve(self.store, spec)
        self.assertEqual(self.engine.check(["native.fixture"])["status"], "complete")

    def test_coverage_gaps_have_distinct_snapshot_identity(self):
        clean = snapshot(self.root, self.config)
        with patch("coding_companion.discovery.os.walk", return_value=[(str(self.root), [], ["missing.py"])]):
            partial = snapshot(self.root, self.config)
        self.assertEqual(clean.files, partial.files)
        self.assertTrue(clean.complete)
        self.assertFalse(partial.complete)
        self.assertNotEqual(clean.snapshot_id, partial.snapshot_id)

    def test_inventory_budget_snapshot_binds_environment_and_policy(self):
        self.write("one.py", "x=1")
        self.write("two.py", "x=2")
        first = snapshot(self.root, replace(self.config, max_inventory_bytes=4))
        second = snapshot(self.root, replace(self.config, max_inventory_bytes=5))
        self.assertEqual(first.files, second.files)
        self.assertFalse(first.complete)
        self.assertFalse(second.complete)
        self.assertNotEqual(first.snapshot_id, second.snapshot_id)
        self.assertEqual(first.environment_hash, self.engine.snapshot().environment_hash)

    def test_javascript_tests_outside_tests_directory_are_preserved(self):
        for path in ("app.test.ts", "src/app.spec.js", "src/app.test.mts", "src/__tests__/case.jsx"):
            self.write(path, "expect(value).toBe(2);")
        self.write("src/app.ts", "export const value = 1;")
        hashes = test_contract_hashes({"argv": []}, self.engine.snapshot())
        self.assertEqual(set(hashes), {"app.test.ts", "src/app.spec.js", "src/app.test.mts", "src/__tests__/case.jsx"})

    def test_weakened_javascript_test_cannot_verify_native_repair(self):
        self.write("app.test.ts", "expect(value).toBe(2);")
        self.native_spec("import sys\nfrom pathlib import Path\nPath(sys.argv[1], 'tests.xml').write_text('<testsuite tests=\"1\"><testcase name=\"regression\"><failure/></testcase></testsuite>')", category="tests", parser="junit")
        failed = self.engine.check(["native.fixture"])
        finding_id = failed["results"][0]["findings"][0]["finding_id"]
        self.write("app.test.ts", "expect(true).toBe(true);")
        self.native_spec("import sys\nfrom pathlib import Path\nPath(sys.argv[1], 'tests.xml').write_text('<testsuite tests=\"1\"><testcase name=\"regression\"/></testsuite>')", category="tests", parser="junit")
        result = self.engine.verify(finding_id)
        self.assertEqual(result["resolution"], "unresolved")
        self.assertIn("verification_blocker", result)


if __name__ == "__main__":
    unittest.main()
