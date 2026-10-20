from __future__ import annotations

import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_release", ROOT / "tools/build_release.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class ReleaseTests(unittest.TestCase):
    def test_wheel_and_source_include_license_and_new_probe_without_state(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(builder, "DIST", Path(directory)):
            release = builder.build()
            with zipfile.ZipFile(release["wheel"]) as wheel:
                prefix = f"coding_companion-{release['version']}.dist-info"
                self.assertEqual(wheel.read(prefix + "/licenses/LICENSE"), (ROOT / "LICENSE").read_bytes())
                self.assertIn(b"License-Expression: MIT", wheel.read(prefix + "/METADATA"))
                self.assertIn("coding_companion/scenario_probe.py", wheel.namelist())
                self.assertIn("coding_companion/js_resolution.py", wheel.namelist())
                self.assertFalse(any(".companion/" in name or "__pycache__" in name for name in wheel.namelist()))
            with zipfile.ZipFile(release["source_zip"]) as source:
                prefix = f"coding-companion-{release['version']}/"
                self.assertEqual(source.read(prefix + "LICENSE"), (ROOT / "LICENSE").read_bytes())
                self.assertIn(prefix + "design/requirements.json", source.namelist())
