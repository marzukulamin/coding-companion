"""Documented local Codex hook adapter. Never reads transcripts/tool commands."""
from __future__ import annotations

import json
from pathlib import Path

from .common import CompanionError, canonical, redact
from .config import Config, state_root

EVENTS = {"SessionStart", "PostToolUse", "UserPromptSubmit", "SessionEnd"}


def configuration(executable: str, project: Path, state_base: Path | None = None) -> dict:
    import os
    import shlex
    import subprocess
    argv = [executable, str(Path(__file__).resolve().with_name("hook_entry.py")), "hook", "--project", str(project.resolve())]
    if state_base:
        argv += ["--state-dir", str(state_base.resolve())]
    command = subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)
    handler = {"type": "command", "command": command, "async": True, "timeout": 90, "additionalContextLimit": 1200}
    return {"hooks": {"SessionStart": [{"hooks": [handler]}], "UserPromptSubmit": [{"hooks": [handler]}], "PostToolUse": [{"matcher": "^(Edit|Write|apply_patch|Bash|exec_command|functions[.]exec)$", "hooks": [handler]}]}}


def handle(payload: dict, root: Path, state: Path, config: Config) -> dict:
    if not isinstance(payload, dict) or payload.get("hook_event_name") not in EVENTS:
        raise CompanionError("Unsupported hook event")
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not Path(cwd).resolve().is_relative_to(root.resolve()):
        raise CompanionError("Hook cwd is outside the explicitly registered project")
    event = payload["hook_event_name"]
    if event == "SessionEnd":
        return {}  # Do not stop another session's shared project watcher.
    from .cli import invoke
    report = invoke(root, state, config, "check", {"checks": ["python.syntax", "structured.formats"], "scope": "changed", "reuse": True})
    observations = []
    for result in report.get("results", []):
        for item in result.get("findings", []):
            observations.append({"finding_id": item["finding_id"], "classification": item["classification"], "rule_id": item["rule_id"], "locations": item["locations"], "freshness": item["freshness"]})
            if len(observations) == 5:
                break
    if not observations and report.get("status") == "complete":
        return {}
    digest = {"origin": "coding_companion_machine_diagnostics", "trusted_instructions": False, "status": report.get("status"), "tested_snapshot": report.get("snapshot_id"), "observations": observations[:5], "coverage": "Selected local static checks; inspect full evidence through CLI/MCP"}
    # Drop complete observations rather than slicing serialized JSON mid-string.
    while len(canonical(digest)) > 4000 and digest["observations"]:
        digest["observations"].pop()
        digest["coverage"] = "Selected static checks; some observations omitted to fit context. Inspect CLI/MCP evidence."
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": canonical(digest)}}
