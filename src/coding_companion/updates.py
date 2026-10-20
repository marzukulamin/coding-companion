"""Reviewed immutable package pointers; installed code is never rewritten."""
from __future__ import annotations

import base64
import csv
import io
import json
import sys
import zipfile
from importlib.resources import files
from pathlib import Path, PurePosixPath

from . import __version__
from .common import CompanionError, atomic_write, canonical, digest, identifier, inside, now, read_bounded


def installed_hash():
    hashes = {}
    def visit(root, prefix=""):
        for item in root.iterdir():
            relative = prefix + item.name
            if item.name == "__pycache__":
                continue
            if item.is_dir():
                visit(item, relative + "/")
            elif PurePosixPath(item.name).suffix in {".py", ".sql", ".json", ".md"}:
                hashes[relative] = digest(item.read_bytes())
    visit(files("coding_companion"))
    return digest(hashes)


def wheel_validate(data: bytes):
    with zipfile.ZipFile(io.BytesIO(data)) as wheel:
        entries = wheel.infolist()
        if len(entries) > 1000 or sum(entry.file_size for entry in entries) > 64 * 1024 * 1024 or len({e.filename for e in entries}) != len(entries):
            raise CompanionError("Package size, count or duplicate-path bound exceeded")
        names = {entry.filename for entry in entries}
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or not (name.startswith("coding_companion/") or ".dist-info/" in name) or path.suffix in {".exe", ".dll", ".pyd", ".so"}:
                raise CompanionError("Package contains an unsupported/unsafe entry")
        record = next((name for name in names if name.endswith(".dist-info/RECORD")), None)
        if not record or "coding_companion/cli.py" not in names:
            raise CompanionError("Expected a complete pure-Python companion wheel")
        checked = set()
        for name, checksum, size in csv.reader(io.StringIO(wheel.read(record).decode("utf-8"))):
            if name not in names or name in checked:
                raise CompanionError("Invalid wheel RECORD identity")
            checked.add(name)
            if name == record:
                if checksum or size:
                    raise CompanionError("RECORD cannot hash itself")
                continue
            body = wheel.read(name)
            encoded = base64.urlsafe_b64encode(bytes.fromhex(digest(body))).rstrip(b"=").decode()
            if checksum != "sha256=" + encoded or size != str(len(body)):
                raise CompanionError("Wheel RECORD hash/size mismatch")
        if checked != names:
            raise CompanionError("Wheel RECORD omits package entries")


def registry(store):
    path = store.state / "packages/registry.json"
    if path.exists():
        return json.loads(read_bounded(path, 65536))
    return {"schema_version": "1.0", "phase": "stable", "active": {"sha256": installed_hash(), "path": None, "schema_min": 1, "schema_max": 2}, "last_known_good": None, "pending": None}


def compatible(store, package):
    version = store.db.execute("SELECT max(version) FROM schema_migrations").fetchone()[0]
    return package["schema_min"] <= version <= package["schema_max"]


def valid_pointer(store, pointer):
    if not pointer or not compatible(store, pointer):
        return False
    if pointer["path"] is None:
        return pointer["sha256"] == installed_hash()
    path = inside(store.state / "packages", Path(pointer["path"]))
    return path.is_file() and digest(read_bounded(path, 64 * 1024 * 1024)) == pointer["sha256"]


def save_registry(store, value):
    atomic_write(store.state / "packages/registry.json", canonical(value).encode())


def reconcile(store):
    value = registry(store)
    if value["phase"] == "pending":
        pending = value["pending"]
        if pending and valid_pointer(store, pending["package"]):
            candidate = store.db.execute("SELECT state,evaluation_passed FROM improvement_candidates WHERE candidate_id=?", (pending["candidate_id"],)).fetchone()
            if candidate and candidate["evaluation_passed"] and candidate["state"] in {"approved", "active"}:
                value["last_known_good"], value["active"] = value["active"], pending["package"]
                store.db.execute("UPDATE improvement_candidates SET state='active',activated_at=? WHERE candidate_id=?", (now(), pending["candidate_id"]))
                value.update(phase="stable", pending=None)
                save_registry(store, value)
                return value
        value.update(phase="stable", pending=None)
    if not valid_pointer(store, value["active"]):
        if not valid_pointer(store, value["last_known_good"]):
            raise CompanionError("No hash-verified DB-compatible active or last-known-good package; preserve state and review recovery")
        value["active"], value["last_known_good"] = value["last_known_good"], None
    save_registry(store, value)
    return value


def evaluate(store, proposal_path: Path, evidence_path: Path, accept_external: bool):
    from .ownership import Ownership
    with Ownership(store.state / "packages/install"):
        return _evaluate(store, proposal_path, evidence_path, accept_external)


def _evaluate(store, proposal_path: Path, evidence_path: Path, accept_external: bool):
    proposal = json.loads(read_bounded(proposal_path, 65536))
    required = {"kind", "package_path", "base_package_sha256", "evaluator_path", "evaluator_sha256", "fixtures_path", "fixtures_sha256", "distribution_rights", "schema_min", "schema_max"}
    if not isinstance(proposal, dict) or set(proposal) != required or proposal["kind"] != "code" or proposal["distribution_rights"] is not True or type(proposal["schema_min"]) is not int or type(proposal["schema_max"]) is not int:
        raise CompanionError("Package proposal needs exact hashes, independent evaluator/fixtures, distribution rights and schema range")
    current = reconcile(store)
    if current["active"]["sha256"] != proposal["base_package_sha256"]:
        raise CompanionError("Proposal base hash does not match the active package")
    package = read_bounded(Path(proposal["package_path"]), 64 * 1024 * 1024)
    package_hash = digest(package)
    wheel_validate(package)
    if digest(read_bounded(Path(proposal["evaluator_path"]), 5 * 1024 * 1024)) != proposal["evaluator_sha256"] or digest(read_bounded(Path(proposal["fixtures_path"]), 5 * 1024 * 1024)) != proposal["fixtures_sha256"]:
        raise CompanionError("Independent evaluator or held-out fixture bytes changed")
    if not compatible(store, proposal):
        raise CompanionError("Candidate is incompatible with the current database schema")
    if not accept_external:
        raise CompanionError("Candidate code is not executed without verified isolation. Supply independently produced evidence and --accept-external-evaluation to record an explicit external attestation")
    evidence = json.loads(read_bounded(evidence_path, 1024 * 1024))
    expected = {"base_package_sha256": proposal["base_package_sha256"], "package_sha256": package_hash, "evaluator_sha256": proposal["evaluator_sha256"], "fixtures_sha256": proposal["fixtures_sha256"]}
    checks = evidence.get("checks")
    if not all(evidence.get(key) == value for key, value in expected.items()) or not isinstance(checks, list) or not checks or any(not isinstance(check, dict) or check.get("outcome") != "passed" or check.get("executed", 0) <= 0 for check in checks) or evidence.get("independent") is not True:
        raise CompanionError("External evaluation does not bind suitable passed evidence to these exact package/evaluator/fixture hashes")
    candidate = identifier()
    target = store.state / "packages" / f"{package_hash}.whl"
    if target.exists() and digest(read_bounded(target, 64 * 1024 * 1024)) != package_hash:
        raise CompanionError("Immutable staged package hash mismatch")
    if not target.exists():
        atomic_write(target, package)
    recorded = {**proposal, "staged_path": str(target), "package_sha256": package_hash}
    store.insert("improvement_candidates", candidate_id=candidate, kind="code", base_version=__version__, base_package_sha256=proposal["base_package_sha256"], proposed_hash=digest(recorded), evaluator_sha256=proposal["evaluator_sha256"], heldout_fixture_sha256=proposal["fixtures_sha256"], proposal_json=canonical(recorded), evaluation_json=canonical({"passed": True, "basis": "explicit_external_attestation", "evidence_hash": digest(evidence), "checks": checks}), state="evaluated", evaluation_passed=1, approval_json="{}", created_at=now())
    return {"status": "evaluated", "candidate_id": candidate, "package_sha256": package_hash, "basis": "User-authorized independent external attestation; candidate code was not executed by this command"}


def manage(store, action, candidate_id=None, approve=False):
    if action in {"activate", "rollback", "recover"}:
        from .ownership import Ownership
        with Ownership(store.state / "packages/install"):
            return _manage(store, action, candidate_id, approve)
    return _manage(store, action, candidate_id, approve)


def _manage(store, action, candidate_id=None, approve=False):
    value = reconcile(store)
    if action in {"status", "recover"}:
        return value
    if action == "rollback":
        if not valid_pointer(store, value["last_known_good"]):
            raise CompanionError("No verified DB-compatible last-known-good package. A DB restore needs separate reconciliation of later observations")
        value["active"], value["last_known_good"] = value["last_known_good"], value["active"]
        save_registry(store, value)
        store.audit("package_rollback", "package", value["active"]["sha256"])
        return value
    if action != "activate" or not approve:
        raise CompanionError("Package activation requires review and --approve")
    row = store.db.execute("SELECT * FROM improvement_candidates WHERE candidate_id=? AND kind='code'", (candidate_id,)).fetchone()
    if not row or row["state"] != "evaluated" or not row["evaluation_passed"]:
        raise CompanionError("Package candidate has no successful reviewed evaluation")
    proposal = json.loads(row["proposal_json"])
    if digest(proposal) != row["proposed_hash"] or value["active"]["sha256"] != row["base_package_sha256"]:
        raise CompanionError("Candidate or active base changed")
    if digest(read_bounded(Path(proposal["evaluator_path"]), 5 * 1024 * 1024)) != row["evaluator_sha256"] or digest(read_bounded(Path(proposal["fixtures_path"]), 5 * 1024 * 1024)) != row["heldout_fixture_sha256"]:
        raise CompanionError("Pinned evaluator/fixtures changed since evaluation")
    pointer = {"sha256": proposal["package_sha256"], "path": proposal["staged_path"], "schema_min": proposal["schema_min"], "schema_max": proposal["schema_max"]}
    if not valid_pointer(store, pointer):
        raise CompanionError("Candidate bytes or schema compatibility failed")
    backup = store.state / "packages/backups" / f"{candidate_id}.sqlite"
    backup.parent.mkdir(parents=True, exist_ok=True)
    store.backup(backup)
    store.db.execute("UPDATE improvement_candidates SET state='approved',approval_json=? WHERE candidate_id=?", (canonical({"actor": "user", "proposed_hash": row["proposed_hash"], "backup": str(backup)}), candidate_id))
    value.update(phase="pending", pending={"candidate_id": candidate_id, "package": pointer})
    save_registry(store, value)
    return reconcile(store)


def launch_active(store, arguments, value):
    import os
    import threading
    import time
    from .processes import launch, close
    from .common import redact
    active = value["active"]
    if not Path(active["path"] or "").is_file() or digest(read_bounded(Path(active["path"]), 64 * 1024 * 1024)) != active["sha256"]:
        raise CompanionError("Active package hash changed before launch")
    if active["path"] is None:
        raise CompanionError("Active package is the installed/source baseline; invoke its normal CLI directly")
    argv = list(arguments or ["doctor", "--json"])
    bootstrap = f"import sys;sys.path.insert(0,{active['path']!r});from coding_companion.cli import main;raise SystemExit(main({argv!r}))"
    env = {key: val for key, val in os.environ.items() if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
    process = launch([sys.executable, "-I", "-c", bootstrap], store.root, env, store.config)
    output, lock, exceeded = bytearray(), threading.Lock(), threading.Event()
    def drain(pipe):
        try:
            while data := pipe.read(4096):
                with lock:
                    remaining = store.config.max_output_bytes - len(output)
                    output.extend(data[:remaining])
                    if len(data) > remaining:
                        exceeded.set()
        finally:
            pipe.close()
    threads = [threading.Thread(target=drain, args=(pipe,), daemon=True) for pipe in (process.stdout, process.stderr)]
    for thread in threads:
        thread.start()
    started, incomplete = time.monotonic(), False
    try:
        while process.poll() is None:
            if exceeded.is_set() or time.monotonic() - started > store.config.timeout_seconds:
                incomplete = True
                break
            time.sleep(0.02)
    finally:
        close(process)
        for thread in threads:
            thread.join(timeout=1)
    return {"status": "incomplete" if incomplete or exceeded.is_set() else "complete" if process.returncode == 0 else "failed", "exit_code": process.returncode, "active_package_sha256": active["sha256"], "output": redact(bytes(output).decode("utf-8", errors="replace"))}
