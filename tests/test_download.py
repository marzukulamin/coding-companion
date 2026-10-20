from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("download_release", ROOT / "tools/download_release.py")
downloader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(downloader)


class DownloadTests(unittest.TestCase):
    def test_exact_private_pin_and_no_credential_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "fixture.whl"
            with zipfile.ZipFile(fixture, "w") as archive:
                archive.writestr("coding_companion-0.4.0.dist-info/METADATA", "Name: coding-companion\nVersion: 0.4.0\n")
            digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
            def fake_run(argv, **kwargs):
                if argv[1] == "api":
                    kwargs["stdout"].write(json.dumps({"private": True}).encode())
                else:
                    self.assertIn("v0.4.0", argv)
                    self.assertEqual(argv[argv.index("--repo") + 1], "owner/private")
                    destination = Path(argv[argv.index("--dir") + 1]) / argv[argv.index("--pattern") + 1]
                    destination.write_bytes(fixture.read_bytes())
                return subprocess.CompletedProcess(argv, 0)
            with patch.object(downloader.subprocess, "run", side_effect=fake_run):
                output = root / "download.whl"
                result = downloader.download("owner/private", "0.4.0", digest, output, executable="gh")
                self.assertEqual(result["status"], "verified_download")
                self.assertEqual(output.read_bytes(), fixture.read_bytes())
                self.assertEqual(sorted(path.name for path in root.iterdir()), ["download.whl", "fixture.whl"])
                with self.assertRaises(ValueError):
                    downloader.download("owner/private", "0.4.0", digest, output, executable="gh")
                with self.assertRaises(ValueError):
                    downloader.download("owner/private", "0.4.0", "0" * 64, root / "bad.whl", executable="gh")
                self.assertFalse((root / "bad.whl").exists())

    def test_public_repository_and_floating_version_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            def fake_run(argv, **kwargs):
                kwargs["stdout"].write(b'{"private":false}')
                return subprocess.CompletedProcess(argv, 0)
            with patch.object(downloader.subprocess, "run", side_effect=fake_run) as invocation:
                with self.assertRaises(ValueError):
                    downloader.download("owner/public", "0.4.0", "0" * 64, Path(temporary) / "release.whl", executable="gh")
                self.assertEqual(invocation.call_count, 1)
                with self.assertRaises(ValueError):
                    downloader.download("owner/private", "latest", "0" * 64, Path(temporary) / "release.whl", executable="gh")
                self.assertEqual(invocation.call_count, 1)
