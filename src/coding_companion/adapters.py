"""Nonexecuting project tool proposals; approval remains a separate operation."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def proposals(inventory: dict, snap=None) -> list[dict]:
    items = []
    languages = set(inventory["languages"])
    frameworks = set(inventory.get("frameworks", []))
    if "python" in languages:
        items.append({"adapter": "python.unittest", "check_id": "native.unittest", "argv": [sys.executable, str(Path(__file__).resolve().with_name("junit_probe.py")), "--report", "{artifact_dir}/tests.xml"], "inputs": ["*.py", "*.toml", "*.cfg", "*.ini"], "parser": "junit", "report": "tests.xml", "category": "tests", "prerequisites": ["Explicit command/input trust"], "detected": any(Path(item["path"]).name == "pyproject.toml" for item in inventory.get("packages", []))})
        items.append({"adapter": "python.pytest", "check_id": "native.pytest", "argv": [sys.executable, "-m", "pytest", "--junitxml", "{artifact_dir}/tests.xml"], "inputs": ["*.py", "*.toml", "*.ini", "*.cfg", "*requirements*.txt"], "parser": "junit", "report": "tests.xml", "category": "tests", "prerequisites": ["Installed pytest", "Explicit command/input trust"], "detected": "pytest" in frameworks})
    for language, executable, args, category in (("go", "go", ["vet", "./..."], "source"), ("rust", "cargo", ["check", "--locked", "--offline"], "build"), ("csharp", "dotnet", ["build", "--no-restore"], "build"), ("java", "mvn", ["-o", "compile"], "build")):
        if language in languages:
            tool = shutil.which(executable)
            items.append({"adapter": language, "check_id": "native." + executable, "argv": [tool or executable, *args], "inputs": ["*"], "parser": "exit_code", "report": None, "category": category, "prerequisites": ["Installed tool/dependencies", "Explicit command/input trust"], "available": tool is not None, "detected": True})
    # npm is a Windows shell shim; propose an explicit Node invocation when possible.
    node = shutil.which("node")
    for command in inventory.get("commands", []):
        name = command.get("name")
        if name in {"build", "lint", "typecheck"}:
            items.append({"adapter": "package.script", "name": name, "package": command["package"], "source_hash": command["source_hash"], "available": node is not None, "trust": "unreviewed", "instructions": "Use the installed package manager's native executable/Node CLI path and approve the exact argv; no shell script is automatically executed"})
    if snap is not None:
        from .web_adapters import proposals as web_proposals
        items.extend(web_proposals(inventory, snap))
    return items
