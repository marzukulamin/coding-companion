from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
import tempfile
import ast
from pathlib import Path

from .common import CompanionError, atomic_write, canonical, digest, identifier, inside, now, read_bounded, redact
from .contracts import Check, Result, finding
from .parsers import junit, sarif
from .processes import launch, terminate, close
from . import __version__


def validate_spec(spec: dict) -> dict:
    required = {"check_id", "argv", "inputs", "parser", "report", "category"}
    if not isinstance(spec, dict) or set(spec) != required:
        raise CompanionError("Native spec must contain exactly check_id, argv, inputs, parser, report, category")
    if not isinstance(spec["check_id"], str) or not re.fullmatch(r"native\.[A-Za-z0-9_.-]{1,120}", spec["check_id"]):
        raise CompanionError("Native check ID must start with native.")
    if not isinstance(spec["argv"], list) or not spec["argv"] or len(spec["argv"]) > 100 or any(not isinstance(x, str) or not x or len(x) > 4000 or "\x00" in x for x in spec["argv"]):
        raise CompanionError("Native argv must be a bounded string array")
    if not isinstance(spec["inputs"], list) or not spec["inputs"] or len(spec["inputs"]) > 100 or any(not isinstance(x, str) or not x or ".." in Path(x).parts or Path(x).is_absolute() or ":" in x or "\\" in x for x in spec["inputs"]):
        raise CompanionError("Native inputs must be relative patterns")
    if spec["parser"] not in {"junit", "sarif", "exit_code"} or not isinstance(spec["category"], str) or not spec["category"] or len(spec["category"]) > 128:
        raise CompanionError("Unsupported native parser/category")
    if spec["category"] == "tests" and spec["parser"] != "junit":
        raise CompanionError("Test checks require a count-bearing JUnit report")
    report = spec["report"]
    if spec["parser"] in {"junit", "sarif"} and (not isinstance(report, str) or not report or Path(report).is_absolute() or ".." in Path(report).parts or ":" in report or "\\" in report):
        raise CompanionError("JUnit report must be a relative artifact path")
    if spec["parser"] == "exit_code" and report is not None:
        raise CompanionError("Exit-code checks do not accept a report")
    return spec


def command_files(spec, root):
    bound = {}
    for argument in spec["argv"][1:]:
        if "{artifact_dir}" in argument or argument.startswith("-"):
            continue
        path = Path(argument)
        if not path.is_absolute():
            path = root / path
        if path.is_file():
            if path.is_symlink() or path.is_junction():
                raise CompanionError("Command file arguments cannot be linked")
            bound[argument] = {"path": str(path.resolve()), "sha256": digest(read_bounded(path, 128 * 1024 * 1024))}
            if path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
                for suffix in ("-wal", "-journal"):
                    sidecar = Path(str(path) + suffix)
                    if sidecar.is_file():
                        bound[argument + suffix] = {"path": str(sidecar.resolve()), "sha256": digest(read_bounded(sidecar, 128 * 1024 * 1024))}
    return bound


def module_versions(spec):
    import importlib.metadata
    argv = spec["argv"]
    versions = {}
    if "-m" in argv and argv.index("-m") + 1 < len(argv):
        module = argv[argv.index("-m") + 1].split(".")[0]
        try:
            version = importlib.metadata.version(module.replace("_", "-"))
        except importlib.metadata.PackageNotFoundError:
            version = "stdlib_or_unregistered"
        versions[module] = version
    # Installed Node entry points can be tiny shims. Bind their own package's
    # runtime artifacts too (e.g. TypeScript's tsc.js -> _tsc.js).
    for argument in argv[1:]:
        path = Path(argument)
        if not path.is_absolute() or "node_modules" not in path.parts or not path.is_file():
            continue
        package = next((parent for parent in path.parents if parent.parent.name == "node_modules" or (parent.parent.name.startswith("@") and parent.parent.parent.name == "node_modules")), None)
        if package is None or str(package) in versions:
            continue
        files, total = {}, 0
        for directory, dirs, names in os.walk(package, followlinks=False):
            for name in dirs:
                child = Path(directory) / name
                if child.is_symlink() or child.is_junction():
                    raise CompanionError("Linked installed tool artifacts cannot be bound")
            for name in sorted(names):
                artifact = Path(directory) / name
                if artifact.suffix.lower() not in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".json", ".node", ".wasm", ".exe", ".dll", ".so", ".dylib"}:
                    continue
                body = read_bounded(artifact, 32 * 1024 * 1024)
                total += len(body)
                if total > 128 * 1024 * 1024 or len(files) >= 4096:
                    raise CompanionError("Installed tool provenance exceeds its byte/file budget")
                files[artifact.relative_to(package).as_posix()] = digest(body)
        versions[str(package)] = digest(files)
    return versions


def input_context(records, root):
    context = {}
    for check_id, record in records.items():
        try:
            context[check_id] = {"spec_hash": digest(record["spec"]), "executable_hash": digest(read_bounded(Path(record["executable"]), 128 * 1024 * 1024)), "command_files": command_files(record["spec"], root), "module_versions": module_versions(record["spec"])}
        except (OSError, CompanionError, ValueError) as exc:
            context[check_id] = {"status": "unavailable", "reason": type(exc).__name__}
    return context


def test_contract_hashes(spec, snap):
    hashes = {}
    for path, body in snap.contents.items():
        name = Path(path).name
        if not (name.startswith("test_") or "/tests/" in "/" + path or "/__tests__/" in "/" + path or re.search(r"\.(?:test|spec)\.[cm]?[jt]sx?$", name)):
            continue
        if path.endswith(".py"):
            try:
                tree = ast.parse(body)
                def visit(nodes, prefix=""):
                    for node in nodes:
                        if isinstance(node, ast.ClassDef):
                            visit(node.body, prefix + node.name + ".")
                        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            hashes[path + ":" + prefix + node.name] = digest(ast.dump(node, include_attributes=False).encode())
                visit(tree.body)
            except (SyntaxError, ValueError):
                hashes[path] = digest(body)
        else:
            hashes[path] = digest(body)
    if "--contract" in spec["argv"]:
        index = spec["argv"].index("--contract") + 1
        if index < len(spec["argv"]) and spec["argv"][index] in snap.files:
            path = spec["argv"][index]
            hashes[path] = snap.files[path]["hash"]
    return hashes


def approve(store, spec: dict) -> dict:
    spec = validate_spec(spec)
    if any(redact(argument) != argument or re.match(r"(?i)^--?(?:password|secret|api[-_]?key|token)(?:=|$)", argument) for argument in spec["argv"]):
        raise CompanionError("Do not place credential literals in probe arguments")
    executable = shutil.which(spec["argv"][0])
    if executable is None:
        raise CompanionError("Native executable is unavailable")
    executable_path = Path(executable).resolve()
    if executable_path.suffix.lower() in {".bat", ".cmd", ".ps1"}:
        raise CompanionError("Use a native executable; shell shims are not supported")
    from .discovery import snapshot
    store.check_privacy()
    store.check_budget()
    snap = snapshot(store.root, store.config, store.state)
    if not snap.complete:
        raise CompanionError("Native approval requires a complete current input snapshot")
    store.save_snapshot(snap)
    import fnmatch
    hashes = {path: meta["hash"] for path, meta in snap.files.items() if any(fnmatch.fnmatch(path, p) for p in spec["inputs"])}
    if not hashes:
        raise CompanionError("Native approval needs declared existing inputs")
    record = {"spec": spec, "spec_hash": digest(spec), "executable": str(executable_path), "executable_hash": digest(read_bounded(executable_path, 128 * 1024 * 1024)), "approved_inputs": hashes, "trust": "explicit_workspace_execution", "network_isolation": "not_enforced"}
    record["command_files"] = command_files(spec, store.root)
    record["module_versions"] = module_versions(spec)
    record["project_root"] = str(store.root)
    trust = store.state / "trusted-probes.json"
    existing = json.loads(read_bounded(trust, 1024 * 1024)) if trust.exists() else {}
    existing[spec["check_id"]] = record
    atomic_write(trust, canonical(existing).encode())
    store.audit("approve_workspace_probe", "check", spec["check_id"])
    return record


def load_probes(state: Path) -> dict:
    path = state / "trusted-probes.json"
    return json.loads(read_bounded(path, 1024 * 1024)) if path.exists() else {}


def native_check(record: dict) -> Check:
    spec = validate_spec(record["spec"])
    return Check(spec["check_id"], spec["category"], "Explicitly trusted workspace command", (), "integration", version=record["spec_hash"][:16] + "." + __version__, executable=True)


def terminate_tree(process: subprocess.Popen):
    terminate(process)


def run_native(store, record: dict, snap, run_id: str) -> Result:
    scratch = store.state / "scratch"
    scratch.mkdir(exist_ok=True, mode=0o700)
    if scratch.is_symlink() or scratch.is_junction():
        raise CompanionError("Native staging directory cannot be linked")
    with tempfile.TemporaryDirectory(prefix="probe-", dir=scratch) as temporary:
        return _run_native(store, record, snap, run_id, Path(temporary))


def _artifact(store, result: Result, filename: str, text: str, media_type: str) -> str:
    run_id = result.run_id
    relative = f"artifacts/{run_id}/{filename}"
    data = redact(text).encode()
    atomic_write(store.state / relative, data)
    artifact_id = identifier()
    result.artifacts.append(dict(artifact_id=artifact_id, relative_state_path=relative, media_type=media_type, sha256=digest(data), size_bytes=len(data), redaction_state="sanitized", created_at=now(), state="available"))
    return artifact_id


def _run_native(store, record: dict, snap, run_id: str, artifact_dir: Path) -> Result:
    import fnmatch
    spec = validate_spec(record["spec"])
    result = Result(spec["check_id"], snap.snapshot_id, "blocked", "none", {"discovered": None, "executed": None, "skipped": None}, run_id=run_id)
    result.check_version = native_check(record).version
    result.verification_basis = {"command_hash": record["spec_hash"]}
    if spec["category"] == "tests":
        result.verification_basis["test_contract_hashes"] = test_contract_hashes(spec, snap)
    if record.get("project_root") != str(store.root):
        result.reasons = ["Native trust belongs to another project or legacy approval; renew exact trust"]
        return result
    if record.get("trust") != "explicit_workspace_execution" or digest(spec) != record.get("spec_hash"):
        result.reasons = ["Native command has no valid explicit trust"]
        return result
    hashes = {p: m["hash"] for p, m in snap.files.items() if any(fnmatch.fnmatch(p, pattern) for pattern in spec["inputs"])}
    executable = Path(record["executable"])
    if not executable.exists():
        result.reasons = ["Native executable missing"]
        return result
    if hashes != record["approved_inputs"] or digest(read_bounded(executable, 128 * 1024 * 1024)) != record["executable_hash"]:
        result.reasons = ["Command inputs or executable changed; renew exact trust before execution"]
        return result
    if command_files(spec, store.root) != record.get("command_files", {}) or module_versions(spec) != record.get("module_versions", {}):
        result.reasons = ["Command file or module version changed; renew exact trust"]
        return result
    argv = [str(executable), *[part.replace("{artifact_dir}", str(artifact_dir)) for part in spec["argv"][1:]]]
    env = {key: value for key, value in os.environ.items() if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL"}}
    output, mutex, overflow = bytearray(), threading.Lock(), threading.Event()

    def drain(pipe):
        try:
            while True:
                chunk = pipe.read(4096)
                if not chunk:
                    break
                with mutex:
                    remaining = store.config.max_output_bytes - len(output)
                    output.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        overflow.set()
        finally:
            pipe.close()

    started = time.monotonic()
    process = launch(argv, store.root, env, store.config)
    threads = [threading.Thread(target=drain, args=(pipe,), daemon=True) for pipe in (process.stdout, process.stderr)]
    for thread in threads:
        thread.start()
    reason = None
    try:
        while process.poll() is None:
            if getattr(store, "cancel", lambda: False)():
                reason = "Native command cancelled by coordinator request"
                break
            if overflow.is_set():
                reason = "Native output exceeded its byte budget"
                break
            if time.monotonic() - started > store.config.timeout_seconds:
                reason = "Native command timed out"
                break
            time.sleep(0.02)
        if reason:
            terminate_tree(process)
    except BaseException:
        terminate_tree(process)
        raise
    finally:
        close(process)
        for thread in threads:
            thread.join(timeout=1)
    result.exit_code = process.returncode
    artifact_text = redact(bytes(output).decode("utf-8", errors="replace"))
    # Evidence is finalized only after whole-buffer redaction, including split tokens.
    evidence = [_artifact(store, result, "output.txt", artifact_text, "text/plain")]
    if reason or overflow.is_set() or any(thread.is_alive() for thread in threads):
        result.outcome, result.completeness = ("cancelled" if reason and "cancelled" in reason else "inconclusive"), "partial"
        result.reasons = [reason or "Incomplete process output/descendant cleanup"]
        return result
    try:
        if spec["parser"] == "junit":
            report = inside(artifact_dir, artifact_dir / spec["report"])
            report_data = read_bounded(report, store.config.max_output_bytes)
            parsed = junit(report_data)
            evidence.append(_artifact(store, result, "tests.xml", report_data.decode("utf-8-sig"), "application/xml"))
            result.counts = parsed["counts"]
            result.verification_basis.update({key: parsed[key] for key in ("case_ids", "executed_case_ids", "failed_case_ids")})
            failed = bool(parsed["failed"])
        elif spec["parser"] == "sarif":
            report = inside(artifact_dir, artifact_dir / spec["report"])
            report_data = read_bounded(report, store.config.max_output_bytes)
            issues = sarif(report_data)
            evidence.append(_artifact(store, result, "report.sarif", report_data.decode("utf-8-sig"), "application/sarif+json"))
            result.counts = {"discovered": 1, "executed": 1, "skipped": 0}
            failed = bool(issues)
        else:
            result.counts = {"discovered": 1, "executed": 1, "skipped": 0}
            failed = False
    except (OSError, CompanionError, UnicodeError) as exc:
        result.outcome, result.completeness = "execution_error", "none"
        result.reasons = [str(exc)[:2000]]
        return result
    result.outcome = "failed" if process.returncode or failed else "passed"
    result.completeness = "complete"
    if command_files(spec, store.root) != record.get("command_files", {}) or module_versions(spec) != record.get("module_versions", {}):
        result.outcome, result.completeness = "superseded", "partial"
        result.reasons = ["Command file or module version changed during execution"]
    if result.outcome == "failed":
        path = next(iter(hashes))
        result.findings.append(finding(result, path=path, content_hash=hashes[path], rule=spec["check_id"], title=f"Native check failed: {spec['check_id']}", actual=f"Exit code {process.returncode}; sanitized output: artifacts/{run_id}/output.txt", expected="Approved command succeeds and required tests execute without failures", category=spec["category"], classification="check_failure"))
        result.findings[-1]["evidence"] = evidence
    return result
