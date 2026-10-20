from __future__ import annotations

import json
import time
import uuid
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .common import CompanionError, atomic_write, canonical, digest, identifier, now, read_bounded, redact

MAX_MESSAGE = 1024 * 1024
OPERATIONS = {"check", "status", "findings", "inspect", "verify", "report", "memory_search", "challenges", "stop", "discover", "plan", "get_run", "feedback", "suppress", "unsuppress", "withdraw", "maintenance", "ack"}


def privacy_epoch(state):
    path = state / "privacy-epoch.json"
    if not path.exists():
        return 0
    return json.loads(read_bounded(path, 65536))["epoch"]


def response_body(value, state):
    path = state / "privacy-epoch.json"
    if path.exists() and json.loads(read_bounded(path, 65536)).get("pending"):
        return None
    if value.get("privacy_epoch", 0) != privacy_epoch(state):
        return None
    return value.get("result", value)


def stop_requested(state: Path, project_id: str) -> bool:
    """Read-only worker control; the coordinator later commits/deletes requests."""
    for path in sorted((state / "inbox").glob("*.json"))[:100]:
        try:
            request = json.loads(read_bounded(path, MAX_MESSAGE))
            validate(request, project_id)
            if request["operation"] == "stop" and datetime.fromisoformat(request["deadline_at"].replace("Z", "+00:00")) >= datetime.now(timezone.utc):
                return True
        except (OSError, ValueError, CompanionError):
            continue
    return False


def validate(request: dict, project_id: str):
    fields = {"schema_version", "request_id", "project_id", "operation", "args", "created_at", "deadline_at"}
    if not isinstance(request, dict) or set(request) != fields or request["schema_version"] != "1.0" or request["project_id"] != project_id:
        raise CompanionError("Invalid or foreign mailbox request")
    try:
        if str(uuid.UUID(request["request_id"])) != request["request_id"]:
            raise ValueError()
        for key in ("created_at", "deadline_at"):
            if not isinstance(request[key], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", request[key]):
                raise ValueError()
            if not datetime.fromisoformat(request[key].replace("Z", "+00:00")).tzinfo:
                raise ValueError()
    except (ValueError, AttributeError, TypeError) as exc:
        raise CompanionError("Invalid request identity/deadline") from exc
    if not isinstance(request["operation"], str) or request["operation"] not in OPERATIONS or not isinstance(request["args"], dict):
        raise CompanionError("Unknown mailbox operation")
    args = request["args"]
    allowed = {"check": {"checks", "scope", "reuse"}, "plan": {"checks", "scope"}, "findings": {"since"}, "ack": {"since"}, "inspect": {"finding_id"}, "verify": {"finding_id", "lesson"}, "memory_search": {"query"}, "challenges": {"actor"}, "get_run": {"run_id"}, "feedback": {"finding_id", "outcome", "reason"}, "suppress": {"finding_id", "reason", "expires_at"}, "unsuppress": {"suppression_id"}, "withdraw": {"kind", "entity_id"}}.get(request["operation"], set())
    if set(args) - allowed:
        raise CompanionError("Unknown request fields; commands and paths are not accepted")
    if "scope" in args and (not isinstance(args["scope"], str) or args["scope"] not in {"project", "changed", "selected"}):
        raise CompanionError("Invalid check scope")
    if "reuse" in args and type(args["reuse"]) is not bool:
        raise CompanionError("Invalid reuse flag")
    if "checks" in args and (not isinstance(args["checks"], list) or len(args["checks"]) > 100 or any(not isinstance(c, str) or len(c) > 128 for c in args["checks"])):
        raise CompanionError("Invalid check IDs")
    if "since" in args and (type(args["since"]) is not int or args["since"] < 0):
        raise CompanionError("Invalid findings cursor")
    for key in ("finding_id", "run_id", "lesson", "query", "actor", "reason", "outcome", "expires_at", "suppression_id", "entity_id", "kind"):
        if key in args and (not isinstance(args[key], str) or not args[key] or len(args[key]) > (4000 if key == "lesson" else 1000)):
            raise CompanionError("Invalid request argument")
    for operation, key in (("inspect", "finding_id"), ("verify", "finding_id"), ("memory_search", "query")):
        if request["operation"] == operation and key not in args:
            raise CompanionError("Missing request argument")
    if "actor" in args and args["actor"] not in {"all", "coding_agent", "companion", "user", "external_tool"}:
        raise CompanionError("Unknown actor")
    if "outcome" in args and args["outcome"] not in {"resolved", "acknowledged", "investigating", "fixing", "dismissed", "accepted-risk"}:
        raise CompanionError("Unknown feedback outcome")
    if request["operation"] == "get_run" and "run_id" not in args:
        raise CompanionError("Missing run ID")
    if request["operation"] == "feedback" and not {"finding_id", "outcome"}.issubset(args):
        raise CompanionError("Missing feedback identity/outcome")
    required = {"suppress": {"finding_id", "reason"}, "unsuppress": {"suppression_id"}, "withdraw": {"kind", "entity_id"}, "ack": {"since"}}.get(request["operation"], set())
    if not required.issubset(args):
        raise CompanionError("Missing control operation arguments")
    if "kind" in args and args["kind"] not in {"finding", "challenge", "lesson"}:
        raise CompanionError("Unknown withdrawal kind")
    if "expires_at" in args:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", args["expires_at"]) or datetime.fromisoformat(args["expires_at"].replace("Z", "+00:00")).tzinfo is None:
                raise ValueError()
        except ValueError as exc:
            raise CompanionError("Invalid suppression expiry timestamp") from exc


def submit(state: Path, project_id: str, operation: str, args: dict, config, root=None) -> dict:
    request_id = identifier()
    request = {"schema_version": "1.0", "request_id": request_id, "project_id": project_id, "operation": operation, "args": args, "created_at": now(), "deadline_at": (datetime.now(timezone.utc) + timedelta(seconds=config.request_timeout_seconds)).isoformat().replace("+00:00", "Z")}
    validate(request, project_id)
    inbox = state / "inbox"
    inbox.mkdir(parents=True, exist_ok=True, mode=0o700)
    if inbox.is_symlink() or inbox.is_junction():
        raise CompanionError("Mailbox cannot be linked")
    if len(list(inbox.iterdir())) >= config.max_mailbox_files:
        raise CompanionError("Mailbox backpressure: pending request budget reached")
    atomic_write(inbox / f"{request_id}.json", canonical(request).encode())
    response = state / "responses" / f"{request_id}.json"
    started = time.monotonic()
    while time.monotonic() - started < config.request_timeout_seconds:
        if response.exists():
            value = response_body(json.loads(read_bounded(response, MAX_MESSAGE)), state)
            if value is not None:
                return value
        if root is not None:
            # A finite coordinator may exit before receiving this request. Only a
            # successfully acquired OS lock permits taking over its durable inbox.
            from .ownership import Busy, Ownership
            try:
                with Ownership(state):
                    from .storage import Store
                    from .engine import Engine
                    from .cli import Dispatcher
                    store = Store(root, state, config)
                    try:
                        Mailbox(store, Dispatcher(Engine(store))).drain()
                    finally:
                        store.close()
            except Busy:
                pass
        time.sleep(0.1)
    return {"status": "incomplete", "completeness": "none", "request_id": request_id, "reasons": ["Coordinator response timed out; ownership remains with coordinator. Do not run a duplicate check."]}


class Mailbox:
    def __init__(self, store, dispatch):
        self.store, self.dispatch = store, dispatch
        for name in ("inbox", "responses", "quarantine"):
            path = store.state / name
            path.mkdir(exist_ok=True, mode=0o700)
            if path.is_symlink() or path.is_junction():
                raise CompanionError("Mailbox directory cannot be linked")

    def intake(self, path: Path):
        request = json.loads(read_bounded(path, MAX_MESSAGE))
        validate(request, self.store.project_id)
        request_id = request["request_id"]
        if path.name != request_id + ".json":
            raise CompanionError("Mailbox filename does not match request")
        payload_hash = digest(request)
        stored_request = {**request, "args": {key: redact(value) if isinstance(value, str) else value for key, value in request["args"].items()}}
        with self.store.transaction():
            existing = self.store.db.execute("SELECT payload_hash,result_json FROM events WHERE request_id=?", (request_id,)).fetchone()
            if existing:
                if existing[0] != payload_hash:
                    raise CompanionError("Conflicting request ID cannot replace its original response")
            else:
                self.store.insert("events", event_id=request_id, session_id=self.store.session_id, request_id=request_id, producer="cli", event_type="check_request" if request["operation"] == "check" else "query", payload_hash=payload_hash, payload_json=canonical(stored_request), created_at=request["created_at"], received_at=now(), deadline_at=request["deadline_at"], state="queued")
        path.unlink()
        if existing and existing["result_json"]:
            self.publish(request_id, json.loads(existing["result_json"]))

    def publish(self, request_id, value):
        status = value.get("status", "complete")
        envelope = {"schema_version": "1.0", "request_id": request_id, "project_id": self.store.project_id, "privacy_epoch": privacy_epoch(self.store.state), "status": status, "result": value}
        data = canonical(envelope).encode()
        if len(data) > MAX_MESSAGE:
            envelope.update(status="incomplete", result={"status": "incomplete", "completeness": "partial", "reasons": ["Response envelope exceeds byte budget"]})
            data = canonical(envelope).encode()
        atomic_write(self.store.state / "responses" / f"{request_id}.json", data)

    def drain(self, limit: int = 16):
        for path in sorted((self.store.state / "inbox").glob("*.json"))[:limit]:
            try:
                self.intake(path)
            except (OSError, ValueError, CompanionError) as exc:
                self.store.audit("rejected_mailbox_request", "event", path.stem[:128])
                # Retain no rejected payload or secrets; preserve original event/response.
                if path.exists() and not path.is_dir():
                    path.unlink()
        pending = self.store.db.execute("SELECT * FROM events WHERE state='queued' ORDER BY received_at LIMIT ?", (limit,)).fetchall()
        for event in pending:
            request = json.loads(event["payload_json"])
            deadline = datetime.fromisoformat(request["deadline_at"].replace("Z", "+00:00"))
            if deadline < datetime.now(timezone.utc):
                response = {"status": "expired", "completeness": "none", "request_id": event["request_id"]}
                state = "expired"
            else:
                self.store.db.execute("UPDATE events SET state='processing' WHERE event_id=?", (event["event_id"],))
                try:
                    response = self.dispatch(request["operation"], request["args"], event["event_id"])
                except (CompanionError, OSError, ValueError) as exc:
                    response = {"status": "error", "completeness": "none", "reasons": [type(exc).__name__ + ": " + str(exc)[:1000]]}
                state = "processed"
            data = canonical(response).encode()
            if len(data) > MAX_MESSAGE:
                response = {"status": "incomplete", "completeness": "partial", "request_id": event["request_id"], "reasons": ["Response byte limit exceeded; inspect findings/runs in bounded pages"]}
            with self.store.transaction():
                self.store.db.execute("UPDATE events SET state=?,result_json=? WHERE event_id=?", (state, canonical(response), event["event_id"]))
        # Commit-before-publish means a crash can always republish the same response.
        for row in self.store.db.execute("SELECT request_id,result_json FROM events WHERE result_json IS NOT NULL ORDER BY received_at DESC LIMIT 100"):
            target = self.store.state / "responses" / f"{row['request_id']}.json"
            current = json.loads(read_bounded(target, MAX_MESSAGE)) if target.exists() else None
            if current is None or current.get("privacy_epoch", 0) != privacy_epoch(self.store.state):
                self.publish(row["request_id"], json.loads(row["result_json"]))
