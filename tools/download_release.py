"""Download an exact private GitHub wheel using existing gh authentication.

The expected SHA-256 must come from an independently reviewed release record.
This tool downloads and verifies; it never installs or executes the wheel.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


def download(repository, version, expected_sha256, destination, executable=None):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not re.fullmatch(r"\d+\.\d+\.\d+", version) or not re.fullmatch(r"[a-fA-F0-9]{64}", expected_sha256):
        raise ValueError("Explicit owner/repository, exact release version and SHA-256 are required")
    executable = executable or shutil.which("gh")
    if not executable:
        raise ValueError("Install and authenticate GitHub CLI separately")
    destination = Path(destination)
    parent = destination.parent.resolve()
    if destination.exists() or destination.is_symlink() or destination.is_junction() or not parent.is_dir() or any(path.is_symlink() or path.is_junction() for path in (destination.parent, *destination.parent.parents)):
        raise ValueError("Destination must be a new file under an existing unlinked directory")
    asset = f"coding_companion-{version}-py3-none-any.whl"
    with tempfile.TemporaryDirectory(prefix="companion-download-", dir=parent) as temporary:
        staging = Path(temporary)
        metadata = staging / "repository.json"
        with metadata.open("wb") as output:
            completed = subprocess.run([executable, "api", f"repos/{repository}", "--jq", "{private: .private}"], stdout=output, stderr=subprocess.DEVNULL, timeout=60, check=False)
        if completed.returncode != 0 or metadata.stat().st_size > 65536:
            raise ValueError("Authenticated repository lookup failed")
        if json.loads(metadata.read_bytes()).get("private") is not True:
            raise ValueError("This download workflow requires a private repository")
        completed = subprocess.run([executable, "release", "download", f"v{version}", "--repo", repository, "--pattern", asset, "--dir", str(staging)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120, check=False)
        wheel = staging / asset
        if completed.returncode != 0 or not wheel.is_file() or wheel.is_symlink() or wheel.is_junction() or wheel.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Pinned release asset is missing or exceeds its byte limit")
        checksum = hashlib.sha256(wheel.read_bytes()).hexdigest()
        if checksum != expected_sha256.lower():
            raise ValueError("Release SHA-256 does not match the independently supplied pin")
        with zipfile.ZipFile(wheel) as archive:
            if len(archive.infolist()) > 4096 or sum(info.file_size for info in archive.infolist()) > 128 * 1024 * 1024:
                raise ValueError("Wheel contents exceed archive bounds")
            metadata_name = f"coding_companion-{version}.dist-info/METADATA"
            if archive.namelist().count(metadata_name) != 1:
                raise ValueError("Pinned package metadata is missing or ambiguous")
            text = archive.read(metadata_name).decode("utf-8")
            if f"\nVersion: {version}\n" not in "\n" + text or "\nName: coding-companion\n" not in "\n" + text:
                raise ValueError("Wheel package identity differs from the requested pin")
            if archive.testzip() is not None:
                raise ValueError("Wheel archive integrity failed")
        # Exclusive creation prevents replacing user files even if a competitor writes
        # the destination after initial validation. No extraction or execution occurs.
        with destination.open("xb") as output, wheel.open("rb") as source:
            shutil.copyfileobj(source, output)
    return {"status": "verified_download", "repository": repository, "version": version, "sha256": checksum, "path": str(destination.resolve()), "installed": False, "credential_storage": "existing_github_cli_authentication"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(download(args.repository, args.version, args.sha256, args.output), indent=2))
