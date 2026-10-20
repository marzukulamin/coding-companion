"""Build private local ZIP/wheel artifacts without downloading build tooling."""
from __future__ import annotations

import base64
import ast
import csv
import hashlib
import io
import json
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def runtime_version():
    tree = ast.parse((ROOT / "src/coding_companion/__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError("Runtime version is missing")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def archive(destination: Path, entries: dict[str, bytes]):
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (2026, 10, 12, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            output.writestr(info, data)
    with zipfile.ZipFile(destination) as check:
        if check.testzip() is not None:
            raise RuntimeError("Archive integrity failed")


def build() -> dict:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = project["version"]
    if version != runtime_version():
        raise RuntimeError("Package metadata and runtime versions differ")
    for source, packaged in (("design/schema.sql", "src/coding_companion/resources/001_initial.sql"), ("design/runtime_extensions.sql", "src/coding_companion/resources/002_runtime.sql"), ("design/contracts.schema.json", "src/coding_companion/resources/contracts.schema.json"), ("skills/coding-companion/SKILL.md", "src/coding_companion/resources/skill/SKILL.md"), ("skills/coding-companion/references/native-probes.md", "src/coding_companion/resources/skill/references/native-probes.md")):
        if (ROOT / source).read_bytes() != (ROOT / packaged).read_bytes():
            raise RuntimeError(f"Packaged resource differs from maintained source: {source}")
    if (ROOT / "skills/coding-companion/references/scenario-probes.md").read_bytes() != (ROOT / "src/coding_companion/resources/skill/references/scenario-probes.md").read_bytes():
        raise RuntimeError("Packaged scenario reference differs from maintained source")
    package = {}
    for path in sorted((ROOT / "src/coding_companion").rglob("*")):
        if path.is_file() and path.suffix in {".py", ".mjs", ".sql", ".json", ".md"} and "__pycache__" not in path.parts:
            if path.is_symlink() or path.is_junction():
                raise RuntimeError("Linked release input rejected")
            package[path.relative_to(ROOT / "src").as_posix()] = path.read_bytes()
    wheel_entries = dict(package)
    metadata_dir = f"coding_companion-{version}.dist-info"
    metadata = f"Metadata-Version: 2.4\nName: coding-companion\nVersion: {version}\nSummary: {project['description']}\nRequires-Python: {project['requires-python']}\nLicense-Expression: {project['license']}\nLicense-File: LICENSE\n"
    wheel_entries[f"{metadata_dir}/licenses/LICENSE"] = (ROOT / "LICENSE").read_bytes()
    for extra, dependencies in project.get("optional-dependencies", {}).items():
        metadata += f"Provides-Extra: {extra}\n"
        for dependency in dependencies:
            metadata += f"Requires-Dist: {dependency}; extra == '{extra}'\n"
    metadata += "\n"
    wheel_entries[f"{metadata_dir}/METADATA"] = metadata.encode()
    wheel_entries[f"{metadata_dir}/WHEEL"] = b"Wheel-Version: 1.0\nGenerator: coding-companion-offline-build\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    wheel_entries[f"{metadata_dir}/entry_points.txt"] = b"[console_scripts]\ncompanion = coding_companion.cli:main\n"
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name, data in sorted(wheel_entries.items()):
        hashed = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        writer.writerow([name, "sha256=" + hashed, len(data)])
    writer.writerow([f"{metadata_dir}/RECORD", "", ""])
    wheel_entries[f"{metadata_dir}/RECORD"] = record.getvalue().encode()
    prefix = f"coding-companion-{version}/"
    source_entries = {prefix + "src/" + name: data for name, data in package.items()}
    root_files = ["LICENSE", "README.md", "IMPLEMENTATION_GAPS.md", "IMPLEMENTATION_STATUS.md", "pyproject.toml", "companion.py", "companion.example.toml", ".gitignore", "ARCHITECTURE.md", "COMPANION_REQUIREMENTS.md", "IMPLEMENTATION_PLAN.md", "RESEARCH_NOTES.md"]
    for relative in root_files:
        source_entries[prefix + relative] = (ROOT / relative).read_bytes()
    for directory in ("design", "tools", "tests", "skills/coding-companion", ".github/workflows"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and path.suffix in {".py", ".sql", ".json", ".md", ".toml", ".yml", ".yaml"} and "__pycache__" not in path.parts:
                source_entries[prefix + path.relative_to(ROOT).as_posix()] = path.read_bytes()
    DIST.mkdir(exist_ok=True)
    if DIST.is_symlink() or DIST.is_junction():
        raise RuntimeError("Release destination cannot be linked")
    wheel = DIST / f"coding_companion-{version}-py3-none-any.whl"
    bundle = DIST / f"coding-companion-{version}-source.zip"
    archive(wheel, wheel_entries)
    archive(bundle, source_entries)
    checksums = {path.name: sha(path.read_bytes()) for path in (wheel, bundle)}
    (DIST / "SHA256SUMS.txt").write_text("".join(f"{checksum}  {name}\n" for name, checksum in checksums.items()), encoding="utf-8")
    return {"status": "built", "version": version, "wheel": str(wheel), "source_zip": str(bundle), "checksums": checksums, "publication": "local_only", "validation": "Archive integrity; run runtime tests separately"}


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
