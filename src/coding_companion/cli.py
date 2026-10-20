from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from . import __version__
from .checks import CHECKS, PROFILES
from .common import CompanionError, canonical, read_bounded, redact
from .config import Config, load_config, project_id, state_root
from .discovery import discover
from .engine import Engine
from .mailbox import submit
from .native import approve, load_probes
from .ownership import Busy, Ownership
from .storage import Store


def doctor() -> dict:
    issues = []
    if sys.version_info < (3, 12):
        issues.append("Python >= 3.12 required")
    if sqlite3.sqlite_version_info < (3, 38, 0):
        issues.append("SQLite >= 3.38 required")
    fts = False
    try:
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute("SELECT json_valid('{}')")
            db.execute("CREATE TABLE probe (id INTEGER) STRICT")
            try:
                db.execute("CREATE VIRTUAL TABLE search_probe USING fts5(text)")
                fts = True
            except sqlite3.Error:
                pass
    except sqlite3.Error:
        issues.append("SQLite JSON/STRICT support unavailable")
    return {"status": "passed" if not issues else "blocked", "version": __version__, "python": platform.python_version(), "sqlite": sqlite3.sqlite_version, "os": platform.system(), "fts5_available": fts, "memory_search": "bounded_lexical", "core_dependencies": "stdlib", "model_api_required": False, "network_required": False, "host_delivery": "cli_checkpoints", "issues": issues}


def markdown_report(store, engine) -> str:
    engine.refresh_findings()
    status = store.status()
    lines = ["# Coding Companion report", "", f"Project: `{store.project_id}`", f"Runs: {status['runs']}; active findings: {status['active_findings']}", "", "Coverage: selected local static or explicitly trusted native checks only.", "Delivery: CLI checkpoints; automatic host delivery is unverified.", ""]
    rows = store.db.execute("SELECT finding_id FROM findings ORDER BY last_seen_at DESC LIMIT 100").fetchall()
    for row in rows:
        item = store.inspect(row[0])
        observation = item["observation"]
        title = item["title"].replace("\n", " ").replace("`", "'")
        lines.extend([f"- **{item['severity']}** {title} — {item['lifecycle']} ({observation['freshness']})", f"  Finding: `{item['finding_id']}`; tested snapshot: `{observation['snapshot_id']}`"])
    if not rows:
        lines.append("No recorded findings. This does not establish unselected coverage.")
    return "\n".join(lines) + "\n"


class Dispatcher:
    def __init__(self, engine):
        self.engine = engine
        self.stopping = False

    def __call__(self, operation: str, args: dict, event_id=None) -> dict:
        store = self.engine.store
        from .mailbox import validate
        from .common import identifier, now
        validate({"schema_version": "1.0", "request_id": identifier(), "project_id": store.project_id, "operation": operation, "args": args, "created_at": now(), "deadline_at": now()}, store.project_id)
        if operation not in {"status", "stop", "maintenance", "withdraw"}:
            store.check_privacy()
        if operation == "discover":
            return discover(store.root, store.config, store.state)
        if operation == "plan":
            return self.engine.plan(args.get("checks"), args.get("scope", "project"))
        if operation == "get_run":
            row = store.db.execute("SELECT result_json FROM runs WHERE run_id=?", (args["run_id"],)).fetchone()
            if not row:
                raise CompanionError("Unknown run")
            return json.loads(row[0])
        if operation == "ack":
            changed = store.db.execute("UPDATE deliveries SET status='acknowledged',acknowledged_at=? WHERE delivery_id<=? AND status IN ('pending','delivered')", (now(), args["since"])).rowcount
            return {"status": "complete", "acknowledged": changed}
        if operation in {"suppress", "unsuppress", "withdraw", "maintenance"}:
            from .maintenance import suppress, unsuppress, withdraw, maintain
            if operation == "suppress":
                return suppress(store, args["finding_id"], args["reason"], args.get("expires_at"))
            if operation == "unsuppress":
                unsuppress(store, args["suppression_id"])
                return {"status": "complete"}
            if operation == "withdraw":
                return withdraw(store, args["kind"], args["entity_id"])
            return maintain(store)
        if operation == "check":
            if event_id:
                previous = store.db.execute("SELECT result_json FROM runs WHERE event_id=? ORDER BY started_at", (event_id,)).fetchall()
                if previous:
                    # Crash replay must not execute the workspace command a second time.
                    return {"status": "incomplete", "completeness": "partial", "results": [json.loads(r[0]) for r in previous], "reasons": ["Recovered original executions; inspect current evidence or request fresh verification"]}
            return self.engine.check(args.get("checks"), event_id, args.get("scope", "project"), args.get("reuse", False))
        if operation == "status":
            return store.status()
        if operation == "findings":
            self.engine.refresh_findings()
            return store.findings(args.get("since", 0))
        if operation == "inspect":
            self.engine.refresh_findings()
            return store.inspect(args["finding_id"])
        if operation == "verify":
            return self.engine.verify(args["finding_id"], args.get("lesson"))
        if operation == "memory_search":
            self.engine.snapshot()
            return {"lessons": store.search_memory(args["query"]), "context_type": "untrusted_project_diagnostics"}
        if operation == "challenges":
            return {"challenges": store.challenges(args.get("actor", "all"))}
        if operation == "report":
            return {"markdown": markdown_report(store, self.engine)}
        if operation == "stop":
            self.stopping = True
            return {"status": "stopping", "completeness": "complete"}
        if operation == "feedback":
            if args["outcome"] == "resolved":
                return self.engine.verify(args["finding_id"])
            if not args.get("reason"):
                raise CompanionError("Lifecycle feedback needs a reason")
            store.inspect(args["finding_id"])
            state = args["outcome"].replace("-", "_")
            with store.transaction():
                store.db.execute("UPDATE findings SET lifecycle=? WHERE finding_id=?", (state, args["finding_id"]))
                store.journal("user", "Feedback: " + state, args["reason"], args["finding_id"])
            return {"status": state}
        raise CompanionError("Unsupported operation")


def invoke(root: Path, state: Path, config: Config, operation: str, args: dict) -> dict:
    args = {key: value for key, value in args.items() if value is not None}
    try:
        with Ownership(state):
            store = Store(root, state, config)
            try:
                dispatcher = Dispatcher(Engine(store))
                result = dispatcher(operation, args)
                from .mailbox import Mailbox
                Mailbox(store, dispatcher).drain()
                return result
            finally:
                store.close()
    except Busy:
        return submit(state, project_id(root), operation, args, config, root=root)


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", type=Path, default=argparse.SUPPRESS)
    common.add_argument("--state-dir", type=Path, default=argparse.SUPPRESS, help="State base; each canonical project gets its own subdirectory")
    common.add_argument("--config", type=Path, default=argparse.SUPPRESS, help="Explicit resource-only TOML configuration")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    result = argparse.ArgumentParser(prog="companion", parents=[common])
    result.add_argument("--version", action="version", version=__version__)
    sub = result.add_subparsers(dest="command", required=True)
    for name in ("doctor", "discover", "status", "stop", "mcp"):
        sub.add_parser(name, parents=[common])
    sub.add_parser("hook", parents=[common])
    for name in ("plan", "check", "scan", "preflight"):
        command = sub.add_parser(name, parents=[common])
        command.add_argument("--check", action="append", dest="checks")
        command.add_argument("--profile", choices=[*PROFILES, "integration"], default="fast")
        command.add_argument("--scope", choices=["project", "changed", "selected"], default="project")
    command = sub.add_parser("watch", parents=[common])
    command.add_argument("--once", action="store_true")
    command.add_argument("--max-seconds", type=float)
    command = sub.add_parser("findings", parents=[common])
    command.add_argument("--since", type=int, default=0)
    command = sub.add_parser("ack", parents=[common])
    command.add_argument("--since", type=int, required=True)
    command = sub.add_parser("get-run", parents=[common])
    command.add_argument("run_id")
    for name in ("inspect", "verify", "feedback"):
        command = sub.add_parser(name, parents=[common])
        command.add_argument("finding_id")
        if name != "inspect":
            command.add_argument("--lesson")
        if name == "feedback":
            command.add_argument("--outcome", choices=["resolved", "acknowledged", "investigating", "fixing", "dismissed", "accepted-risk"], required=True)
            command.add_argument("--reason")
    command = sub.add_parser("report", parents=[common])
    command.add_argument("--format", choices=["markdown", "json"], default="markdown")
    command = sub.add_parser("challenges", parents=[common])
    command.add_argument("--actor", choices=["all", "coding_agent", "companion", "user", "external_tool"], default="all")
    command.add_argument("--record", metavar="SYMPTOMS")
    command.add_argument("--goal", default="Diagnose and verify")
    command = sub.add_parser("memory", parents=[common])
    command.add_argument("action", choices=["search", "inspect", "delete", "export"])
    command.add_argument("value", nargs="?")
    command.add_argument("--output", type=Path)
    command = sub.add_parser("probe", parents=[common])
    command.add_argument("action", choices=["propose", "approve", "list", "revoke"])
    command.add_argument("value", nargs="?")
    command.add_argument("--output", type=Path, help="Save one proposed spec for review; requires its check ID")
    command.add_argument("--trust-workspace-execution", action="store_true", help="Explicitly trust this exact command, executable and input hashes; no OS/network isolation is claimed")
    command = sub.add_parser("backup", parents=[common])
    command.add_argument("destination", type=Path)
    command = sub.add_parser("suppress", parents=[common])
    command.add_argument("finding_id")
    command.add_argument("--reason", required=True)
    command.add_argument("--expires-at")
    command = sub.add_parser("unsuppress", parents=[common])
    command.add_argument("suppression_id")
    sub.add_parser("maintenance", parents=[common])
    command = sub.add_parser("withdraw", parents=[common])
    command.add_argument("kind", choices=["finding", "challenge", "lesson"])
    command.add_argument("entity_id")
    command = sub.add_parser("host", parents=[common])
    command.add_argument("action", choices=["plan", "install", "uninstall"])
    command.add_argument("host", choices=["manual", "codex", "claude", "mcp"])
    command.add_argument("--destination", type=Path)
    command = sub.add_parser("improve", parents=[common])
    command.add_argument("action", choices=["plan", "evaluate", "activate", "rollback"])
    command.add_argument("--proposal", type=Path)
    command.add_argument("--candidate")
    command.add_argument("--approve", action="store_true")
    command = sub.add_parser("learning", parents=[common])
    command.add_argument("action", choices=["train", "list", "activate", "score", "revoke"])
    command.add_argument("--dataset", type=Path)
    command.add_argument("--artifact")
    command.add_argument("--text")
    command.add_argument("--authorize-local-training", action="store_true")
    command.add_argument("--approve", action="store_true")
    command = sub.add_parser("update", parents=[common])
    command.add_argument("action", choices=["status", "evaluate", "activate", "rollback", "recover", "launch"])
    command.add_argument("--proposal", type=Path)
    command.add_argument("--evidence", type=Path)
    command.add_argument("--candidate")
    command.add_argument("--accept-external-evaluation", action="store_true")
    command.add_argument("--approve", action="store_true")
    command.add_argument("--run-args", nargs=argparse.REMAINDER)
    command = sub.add_parser("benchmark", parents=[common])
    command.add_argument("--results", type=Path, required=True)
    return result


def run(args) -> dict:
    if args.command == "doctor":
        return doctor()
    root = args.project.resolve()
    if not root.is_dir():
        raise CompanionError("Project root does not exist")
    config = load_config(args.config)
    state = state_root(root, args.state_dir)
    if args.command == "benchmark":
        from .evaluation import paired
        return paired(json.loads(read_bounded(args.results, 5 * 1024 * 1024)))
    if args.command == "discover":
        return discover(root, config, state)
    if args.command == "mcp":
        from .mcp_adapter import serve
        return serve(root, state, config)
    if args.command == "hook":
        from .hooks import handle
        data = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise CompanionError("Hook input exceeded its bound")
        return handle(json.loads(data), root, state, config)
    remote_operations = {"check", "scan", "preflight", "status", "stop", "findings", "inspect", "verify", "report", "suppress", "unsuppress", "withdraw", "maintenance", "ack", "get-run"}
    if args.command in remote_operations:
        operation = "check" if args.command in {"scan", "preflight"} else "get_run" if args.command == "get-run" else args.command
        params = {}
        if operation == "check":
            if args.profile == "integration" and not args.checks:
                raise CompanionError("Integration profile requires explicit approved --check IDs")
            params["checks"] = args.checks or PROFILES.get(args.profile)
            params["scope"] = args.scope
        if operation in {"findings", "ack"}:
            if args.since < 0:
                raise CompanionError("Cursor cannot be negative")
            params["since"] = args.since
        if operation in {"inspect", "verify"}:
            params["finding_id"] = args.finding_id
        if operation == "verify" and args.lesson:
            params["lesson"] = args.lesson
        if operation == "get_run":
            params["run_id"] = args.run_id
        if operation == "suppress":
            params = {"finding_id": args.finding_id, "reason": args.reason, "expires_at": args.expires_at}
        if operation == "unsuppress":
            params = {"suppression_id": args.suppression_id}
        if operation == "withdraw":
            params = {"kind": args.kind, "entity_id": args.entity_id}
        return invoke(root, state, config, operation, params)
    if args.command == "host":
        from .host import manage_host
        return manage_host(args.action, args.host, args.destination)
    if args.command == "update" and args.action == "launch":
        from .updates import launch_active, manage
        from types import SimpleNamespace
        with Ownership(state / "packages/install"):
            with Ownership(state):
                active_store = Store(root, state, config)
                try:
                    value = manage(active_store, "status")
                    if value["active"]["path"] is None:
                        raise CompanionError("Invoke the baseline CLI directly")
                finally:
                    active_store.close()
            return launch_active(SimpleNamespace(state=state, root=root, config=config), args.run_args, value)
    with Ownership(state):
        store = Store(root, state, config)
        engine = Engine(store)
        dispatch = Dispatcher(engine)
        try:
            if args.command == "watch":
                if args.max_seconds is not None and args.max_seconds <= 0:
                    raise CompanionError("Watch duration must be positive")
                from .watch import watch
                return watch(engine, dispatch, lambda: dispatch.stopping, once=args.once, max_seconds=args.max_seconds)
            if args.command == "plan":
                if args.profile == "integration" and not args.checks:
                    raise CompanionError("Integration plan requires explicit check IDs")
                report = engine.plan(args.checks or PROFILES.get(args.profile), args.scope)
                return report
            if args.command == "feedback":
                if args.outcome == "resolved":
                    return engine.verify(args.finding_id, args.lesson)
                if not args.reason:
                    raise CompanionError("Lifecycle feedback requires a reason")
                store.inspect(args.finding_id)
                lifecycle = args.outcome.replace("-", "_")
                with store.transaction():
                    store.db.execute("UPDATE findings SET lifecycle=? WHERE finding_id=?", (lifecycle, args.finding_id))
                    store.journal("user", f"Feedback: {lifecycle}", args.reason, args.finding_id)
                    store.audit("feedback_" + lifecycle, "finding", args.finding_id)
                return {"status": lifecycle, "finding_id": args.finding_id}
            if args.command == "memory":
                if args.action == "search":
                    return dispatch("memory_search", {"query": args.value or ""})
                if args.action == "delete":
                    store.delete_lesson(args.value)
                    return {"status": "deleted", "lesson_id": args.value, "backup_note": "Previously exported backups are outside live deletion scope"}
                if args.action == "inspect":
                    row = store.db.execute("SELECT * FROM lessons WHERE lesson_id=?", (args.value,)).fetchone()
                    if not row:
                        raise CompanionError("Unknown lesson")
                    return dict(row)
                if args.output:
                    return store.export_memory(args.output)
                return {"scope": "project_private", "lessons": [dict(r) for r in store.db.execute("SELECT * FROM lessons WHERE status='verified' LIMIT 100")]}
            if args.command == "challenges":
                if args.record:
                    return {"challenge_id": store.journal("user" if args.actor == "all" else args.actor, args.goal, args.record)}
                return dispatch("challenges", {"actor": args.actor})
            if args.command == "probe":
                if args.action == "propose":
                    proposals = discover(root, config, state)["native_proposals"]
                    if args.value:
                        proposals = [item for item in proposals if item.get("check_id") == args.value]
                        if len(proposals) != 1:
                            raise CompanionError("Unknown or ambiguous proposal check ID")
                    if args.output:
                        if not args.value or not proposals[0].get("spec"):
                            raise CompanionError("Saving a proposal requires one available check ID")
                        if args.output.exists():
                            raise CompanionError("Proposal output already exists; choose a new review file")
                        from .common import atomic_write
                        atomic_write(args.output, canonical(proposals[0]["spec"]).encode())
                    return {"status": "proposed", "proposals": proposals, "output": str(args.output.resolve()) if args.output else None, "trust": "unreviewed"}
                if args.action == "list":
                    return {"probes": load_probes(state)}
                if args.action == "approve":
                    if not args.trust_workspace_execution or not args.value:
                        raise CompanionError("Probe approval needs a spec path and --trust-workspace-execution")
                    engine.snapshot()
                    spec = json.loads(read_bounded(Path(args.value), 65536))
                    return approve(store, spec)
                probes = load_probes(state)
                if args.value not in probes:
                    raise CompanionError("Unknown approved probe")
                from .common import atomic_write
                del probes[args.value]
                atomic_write(state / "trusted-probes.json", canonical(probes).encode())
                return {"status": "revoked", "check_id": args.value}
            if args.command == "backup":
                store.backup(args.destination)
                return {"status": "complete", "backup": str(args.destination.resolve())}
            if args.command in {"suppress", "unsuppress", "maintenance", "withdraw"}:
                from .maintenance import maintain, suppress, unsuppress, withdraw
                if args.command == "suppress":
                    return suppress(store, args.finding_id, args.reason, args.expires_at)
                if args.command == "unsuppress":
                    unsuppress(store, args.suppression_id)
                    return {"status": "complete"}
                if args.command == "withdraw":
                    return withdraw(store, args.kind, args.entity_id)
                return maintain(store)
            if args.command == "improve":
                from .improvement import manage_improvement
                return manage_improvement(store, engine, args)
            if args.command == "learning":
                from .learning import manage, train
                if args.action == "train":
                    if args.dataset is None:
                        raise CompanionError("Training needs an explicitly supplied --dataset")
                    return train(store, args.dataset, args.authorize_local_training)
                return manage(store, args.action, args.artifact, args.text, args.approve)
            if args.command == "update":
                from .updates import evaluate, launch_active, manage
                if args.action == "evaluate":
                    if args.proposal is None or args.evidence is None:
                        raise CompanionError("Package evaluation needs --proposal and independently produced --evidence")
                    return evaluate(store, args.proposal, args.evidence, args.accept_external_evaluation)
                return manage(store, args.action, args.candidate, args.approve)
            raise CompanionError("Command not implemented")
        finally:
            if store is not None:
                store.close()


def exit_code(report: dict) -> int:
    if report.get("status") == "failed":
        return 1
    if report.get("status") in {"blocked", "incomplete", "expired", "error"} or report.get("completeness") in {"partial", "none"}:
        return 2
    return 0


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    for key, default in {"project": Path.cwd(), "state_dir": None, "config": None, "json": False}.items():
        if not hasattr(args, key):
            setattr(args, key, default)
    try:
        report = run(args)
        if args.command == "mcp":
            return exit_code(report)
        if args.command == "report" and not args.json and args.format == "markdown" and "markdown" in report:
            print(report["markdown"], end="")
        else:
            print(json.dumps(report, ensure_ascii=True, indent=2))
        return exit_code(report)
    except KeyboardInterrupt:
        print(canonical({"status": "cancelled", "completeness": "none"}), file=sys.stderr)
        return 130
    except (CompanionError, OSError, ValueError, sqlite3.Error, KeyError, TypeError) as exc:
        print(canonical({"status": "error", "completeness": "none", "reason": redact(str(exc))[:2000]}), file=sys.stderr)
        return 2
