from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

from .common import CompanionError, atomic_write, canonical, digest, read_bounded

OWNED = ("SKILL.md", "references/native-probes.md", "references/scenario-probes.md")


def manage_host(action: str, host: str, destination: Path | None):
    plan = {"host": host, "adapter": "portable_skill_cli", "delivery": "cli_checkpoints", "live_hooks": "unverified_not_installed", "mcp": "optional_sdk_adapter_not_host_certified", "runtime_prerequisite": "Install companion or retain an accessible source checkout", "destination": str(destination) if destination else None, "configuration_changes": "none", "scheduler_installed": False}
    if action == "plan":
        if host == "codex":
            from .hooks import configuration
            import sys
            plan["hook_configuration"] = configuration(sys.executable, Path.cwd())
            plan["hook_delivery"] = "Documented local safe-point delivery; real Codex session certification pending"
        return plan
    if destination is None:
        raise CompanionError("Skill install/uninstall requires an explicit --destination directory")
    target = destination.resolve()
    # Do not silently merge with a skill or overwrite user configuration.
    if action == "install":
        if target.exists():
            raise CompanionError("Installation target exists; choose a new skill directory")
        parent = target.parent
        if not parent.is_dir() or parent.is_symlink() or parent.is_junction():
            raise CompanionError("Installation parent must be an existing unlinked directory")
        source = files("coding_companion").joinpath("resources/skill")
        manifest = {}
        for relative in OWNED:
            data = source.joinpath(relative).read_bytes()
            atomic_write(target / relative, data)
            manifest[relative] = digest(data)
        atomic_write(target / "companion-install.json", canonical({"owner": "coding-companion", "files": manifest}).encode())
        return {**plan, "status": "installed", "destination": str(target)}
    metadata = target / "companion-install.json"
    record = json.loads(read_bounded(metadata, 65536))
    installed = record.get("files", {})
    if record.get("owner") != "coding-companion" or not isinstance(installed, dict) or set(installed) not in (set(OWNED), set(OWNED[:2])):
        raise CompanionError("Target does not have a valid companion ownership manifest")
    for relative in installed:
        path = target / relative
        if not path.resolve().is_relative_to(target) or digest(read_bounded(path, 65536)) != record["files"][relative]:
            raise CompanionError("Installed skill changed; preserve edits and review removal")
    for relative in installed:
        (target / relative).unlink()
    metadata.unlink()
    for directory in (target / "references", target):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    return {**plan, "status": "uninstalled"}
