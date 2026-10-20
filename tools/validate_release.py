"""Run release gates and retain measured, input-bound results for this host."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sqlite3
import subprocess
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validate(output, optional_dependencies=None, browser_dependencies=None, executable=None, web_project=None, codex_executable=None):
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    logs = ROOT / ".companion" / f"validation-{version}"
    logs.mkdir(parents=True, exist_ok=True)
    gates = [("runtime_tests", ["-m", "unittest", "discover", "-s", "tests", "-q"]),
             ("architecture", ["tools/validate_architecture.py", "--summary"]),
             ("requirements", ["tools/validate_requirements.py"])]
    if optional_dependencies:
        gates.append(("schema_mcp", ["tools/validate_optional.py", "--dependencies", str(optional_dependencies.resolve())]))
    if browser_dependencies and executable:
        options = ["--dependencies", str(browser_dependencies.resolve()), "--executable", str(executable.resolve())]
        gates.extend((name, [script, *options]) for name, script in (("browser", "tools/validate_browser.py"), ("browser_interactions", "tools/validate_browser_interactions.py")))
    elif browser_dependencies or executable:
        raise ValueError("Browser dependencies and executable must be supplied together")
    if web_project:
        gates.append(("web_tools", ["tools/validate_web.py", "--project", str(web_project.resolve())]))
    if codex_executable:
        gates.append(("codex_hooks", ["tools/validate_codex.py", "--executable", str(codex_executable.resolve())]))
    gates.append(("packaging", ["tools/build_release.py"]))
    inputs = {}
    for directory in ("src", "tests", "tools", "design", "skills"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix in {".py", ".mjs", ".md", ".json", ".sql", ".toml"}:
                inputs[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ("pyproject.toml", "LICENSE"):
        inputs[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    results = []
    for name, arguments in gates:
        path = logs / f"{name}.log"
        started = time.monotonic()
        print(f"Validating {name}...", flush=True)
        with path.open("w", encoding="utf-8") as handle:
            try:
                completed = subprocess.run([sys.executable, *arguments], cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, timeout=600, check=False)
                code, status = completed.returncode, "passed" if completed.returncode == 0 else "failed"
            except subprocess.TimeoutExpired:
                code, status = None, "timeout"
        text = path.read_text(encoding="utf-8", errors="replace")
        result = {"gate": name, "status": status, "exit_code": code, "duration_seconds": round(time.monotonic() - started, 3), "log": path.relative_to(ROOT).as_posix(), "log_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        count = re.search(r"Ran (\d+) tests?", text)
        if name == "runtime_tests" and count:
            result["executed_tests"] = int(count.group(1))
        results.append(result)
        if status != "passed":
            break  # Never build a release behind failed gates.
    current_inputs = all((ROOT / name).is_file() and hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == value for name, value in inputs.items())
    record = {"version": version, "created_at": datetime.now(timezone.utc).isoformat(), "platform": platform.system(), "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
              "status": "passed" if len(results) == len(gates) and all(item["status"] == "passed" for item in results) and current_inputs else "failed",
              "inputs_unchanged": current_inputs, "input_hashes": inputs, "gates": results,
              "scope": "Local gates selected by this invocation; synthetic fixtures do not certify actual agent delivery, customer projects or other platforms",
              "unverified": ["Actual active-turn host delivery", "Independent customer-project effectiveness trials", "Other OS/Python versions", "Complete detector catalog", "Isolated automatic candidate execution"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": record["status"], "version": version, "results": results, "record": str(output.resolve())}, indent=2), flush=True)
    return 0 if record["status"] == "passed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/validation.json")
    parser.add_argument("--optional-dependencies", type=Path)
    parser.add_argument("--browser-dependencies", type=Path)
    parser.add_argument("--browser-executable", type=Path)
    parser.add_argument("--web-project", type=Path)
    parser.add_argument("--codex-executable", type=Path)
    args = parser.parse_args()
    raise SystemExit(validate(args.output, args.optional_dependencies, args.browser_dependencies, args.browser_executable, args.web_project, args.codex_executable))
