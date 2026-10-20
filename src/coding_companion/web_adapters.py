"""Read installed Node CLI manifests and propose bounded, shell-free native specs."""
from __future__ import annotations

import shutil
from pathlib import Path

from .common import CompanionError, digest, read_bounded, strict_json

TOOLS = {
    "typescript": ("tsc", "typecheck", "source"),
    "eslint": ("eslint", "lint", "source"),
    "vite": ("vite", "build", "build"),
    "vitest": ("vitest", "tests", "tests"),
}
ESLINT_CONFIGS = tuple("eslint.config." + ext for ext in ("js", "mjs", "cjs", "ts", "mts", "cts"))


def installed_cli(root: Path, package: Path, name: str, binary: str) -> dict:
    """Resolve normal and hoisted installations inside this project only; never import them."""
    for directory in (package, *package.parents):
        if not directory.is_relative_to(root):
            break
        manifest = directory / "node_modules" / name / "package.json"
        if not manifest.exists():
            continue
        try:
            tool_root = manifest.parent.resolve()
            if not tool_root.is_relative_to(root):
                raise CompanionError("Installed tool resolves outside the project")
            metadata = strict_json(read_bounded(manifest, 65536).decode("utf-8-sig"))
            if not isinstance(metadata, dict) or metadata.get("name") != name or not isinstance(metadata.get("version"), str):
                raise CompanionError("Installed tool identity/version is invalid")
            bins = metadata.get("bin")
            target = bins if isinstance(bins, str) else bins.get(binary) if isinstance(bins, dict) else None
            if not isinstance(target, str) or Path(target).is_absolute() or ".." in Path(target).parts or ":" in target or "\\" in target:
                raise CompanionError("Installed tool has an unsafe/missing CLI path")
            cli = tool_root / target
            if not cli.resolve().is_relative_to(tool_root) or cli.suffix not in {"", ".js", ".mjs", ".cjs"}:
                raise CompanionError("Installed CLI must be a local JavaScript file")
            read_bounded(cli, 8 * 1024 * 1024)
            return {"cli": str(cli.resolve()), "version": metadata["version"], "package_manifest": str(manifest.resolve())}
        except (OSError, UnicodeError, ValueError, CompanionError):
            return {"reason": "Installed tool manifest/CLI is unavailable, invalid or outside the project"}
    return {"reason": f"Install {name} in this project before proposing an executable probe"}


def proposals(inventory: dict, snap) -> list[dict]:
    root = Path(inventory["project_root"]).resolve()
    node = shutil.which("node")
    wrapper = str(Path(__file__).resolve().with_name("node_probe.mjs"))
    items = []
    for package in inventory.get("packages", []):
        if package["kind"] != "package.json" or not package["parsed"]:
            continue
        relative = Path(package["path"]).parent.as_posix()
        directory = root / relative
        dependencies = set(package.get("dependencies", []))
        for name, (binary, action, category) in TOOLS.items():
            if name not in dependencies:
                continue
            installed = installed_cli(root, directory, name, binary)
            reasons = [] if node else ["Node native executable is unavailable"]
            if "cli" not in installed:
                reasons.append(installed["reason"])
            config = (Path(relative) / "tsconfig.json").as_posix()
            if name == "typescript" and config not in snap.files:
                reasons.append("This package has no tsconfig.json; select its intended TypeScript project explicitly")
            if name == "typescript":
                args = ["--project", str(directory / "tsconfig.json"), "--noEmit", "--incremental", "--pretty", "false", "--tsBuildInfoFile", "{artifact_dir}/typecheck.tsbuildinfo"]
            elif name == "eslint":
                args = ["."]
                if not any((Path(relative) / p).as_posix() in snap.files for p in ESLINT_CONFIGS):
                    reasons.append("This package has no supported flat ESLint configuration")
            elif name == "vite":
                args = ["build", "--outDir", "{artifact_dir}/build", "--emptyOutDir"]
            else:
                args = ["run", "--reporter=junit", "--outputFile={artifact_dir}/tests.xml"]
            check_id = "native.web." + action + ("." + digest(relative)[:12] if relative != "." else "")
            spec = None if reasons else {"check_id": check_id, "argv": [node, wrapper, str(directory.resolve()), installed["cli"], *args], "inputs": ["*"], "parser": "junit" if category == "tests" else "exit_code", "report": "tests.xml" if category == "tests" else None, "category": category}
            items.append({"adapter": "web." + name, "check_id": check_id, "package": relative, "source_hash": snap.files[package["path"]]["hash"], "detected": True, "available": not reasons, "trust": "unreviewed", "tool_version": installed.get("version"), "spec": spec, "blocked_reasons": reasons, "prerequisites": ["Explicit command/input trust", "Installed tool and its project dependencies"], "scope": "Direct installed tool invocation; custom package scripts are not executed"})
    return items
