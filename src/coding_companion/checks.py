from __future__ import annotations

import ast
import json
import sqlite3
import tomllib
from contextlib import closing
from pathlib import Path

from .contracts import Check, Result, finding
from .discovery import Snapshot
from .packs import PACK_CHECKS, paths_for, run_pack
from .common import strict_json

CHECKS = {
    "python.syntax": Check("python.syntax", "source", "Parse Python without importing or executing it", (".py",)),
    "structured.formats": Check("structured.formats", "configuration", "Parse JSON and TOML inputs", (".json", ".toml")),
    "sqlite.schema": Check("sqlite.schema", "database", "Validate explicitly named SQLite schema files in memory", (".sql",)),
}
CHECKS.update(PACK_CHECKS)
PROFILES = {"fast": ["python.syntax", "structured.formats"], "security": ["security.patterns"], "browser": ["web.semantics"], "data": ["data.contracts"], "rag": ["rag.contracts"], "model": ["ai.contracts", "model.contracts"], "training": ["training.contracts"], "load": ["performance.contracts"], "maintenance": ["python.syntax", "structured.formats"], "full": list(CHECKS)}

# These are coverage declarations, not claims that a generic static scan proves them.
FAMILIES = {
    "C01": "Environment, dependencies, and setup", "C02": "Source, static checks, and production builds", "C03": "Test infrastructure and discovery", "C04": "Test quality and requirement coverage", "C05": "Business logic and input boundaries", "C06": "Rendered UI and interaction", "C07": "Accessibility", "C08": "APIs, integrations, and real-time protocols", "C09": "Identity, authorization, and tenant isolation", "C10": "Security and supply chain", "C11": "Databases", "C12": "Migrations, retention, and recovery", "C13": "Data pipelines", "C14": "Queues, workers, schedules, and caching", "C15": "Concurrency", "C16": "Traffic and capacity", "C17": "Resilience and failure behavior", "C18": "Deployment, networking, and operations", "C19": "RAG ingestion and retrieval", "C20": "AI applications and agents", "C21": "Open-source/local model integration and serving", "C22": "Training and fine-tuning projects", "C23": "Specialized extensions",
}


def applicable_paths(check_id: str, snap: Snapshot) -> list[str]:
    if check_id in PACK_CHECKS:
        return paths_for(check_id, snap)
    check = CHECKS[check_id]
    return [p for p in snap.files if Path(p).suffix in check.suffixes and (check_id != "sqlite.schema" or Path(p).name in {"schema.sql", "memory_fts.sql"})]


def plan(snap: Snapshot, selected: list[str] | None = None) -> dict:
    ids = selected if selected is not None else ["python.syntax", "structured.formats"]
    facets = {"C01": "Static manifests, environment names and installed-tool proposals", "C02": "Python syntax, JSON/TOML and approved native build/lint commands", "C03": "Real unittest/JUnit adapter and count validation", "C05": "Explicit local data/response acceptance contracts", "C06": "Declared loopback rendered-browser assertions; optional Playwright/browser required", "C07": "Local HTML semantics and declared browser visibility/focus assertions; no full accessibility certification", "C08": "Declared loopback HTTP status/header/JSON contracts", "C09": "Captured RAG tenant isolation and explicitly supplied HTTP role scenarios", "C10": "Predicted Python execution risks and trusted native SARIF evidence", "C11": "SQLite schema plus read-only customer SQLite integrity/relations/scalar contracts", "C12": "Companion backup/restore, retention, deletion and DB-compatible package rollback; customer migration automation unavailable", "C13": "Local CSV/JSONL row, uniqueness and relation contracts", "C16": "Supplied measured workload/latency thresholds; no automatic load generator", "C19": "Captured index/retrieval deletion, tenant, version and relevance contracts", "C20": "Captured structured responses, grounding IDs and explicit expectations", "C21": "Declared model identity/context/artifact hashes; no mandatory inference engine", "C22": "Declared rights/split/loss validation and separately authorized local ranking classifier"}
    return {"snapshot_id": snap.snapshot_id, "checks": [{**CHECKS[c].manifest(), "input_count": len(applicable_paths(c, snap)), "status": "applicable" if applicable_paths(c, snap) else "not_applicable"} for c in ids], "coverage_gaps": snap.gaps, "detector_families": [{"id": key, "name": value, "status": "partial" if key in facets else "unavailable", "reason": facets.get(key, "No maintained detector pack for this family; a user-approved native probe may provide explicitly scoped evidence")} for key, value in FAMILIES.items()]}


def run_static(check_id: str, snap: Snapshot, run_id: str | None = None) -> Result:
    if check_id in PACK_CHECKS:
        return run_pack(check_id, snap, run_id)
    check = CHECKS[check_id]
    paths = applicable_paths(check_id, snap)
    result = Result(check_id, snap.snapshot_id, "passed", "complete", {"discovered": len(paths), "executed": 0, "skipped": 0})
    if run_id:
        result.run_id = run_id
    if not paths:
        result.outcome, result.completeness = "not_applicable", "none"
        result.reasons = ["No applicable inputs were discovered"]
        return result
    for path in paths:
        if len(result.findings) >= 1000:
            result.outcome, result.completeness = "inconclusive", "partial"
            result.reasons.append("Finding limit reached; remaining inputs not checked")
            result.counts["skipped"] += len(paths) - result.counts["executed"]
            break
        data = snap.contents[path]
        try:
            if check_id == "python.syntax":
                tree = ast.parse(data, filename=path)
                compile(tree, path, "exec", dont_inherit=True)
            elif check_id == "structured.formats":
                text = data.decode("utf-8-sig")
                strict_json(text) if path.endswith(".json") else tomllib.loads(text)
            elif check_id == "sqlite.schema":
                # Customer scripts are parsed by SQLite's engine under a deny authorizer.
                # Only schema DDL on an empty in-memory database is permitted.
                sql = data.decode("utf-8-sig")
                with closing(sqlite3.connect(":memory:")) as db:
                    denied = {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_PRAGMA}
                    def authorize(action, a, b, c, d):
                        if action in denied:
                            return sqlite3.SQLITE_DENY
                        if action == sqlite3.SQLITE_FUNCTION and b not in {"json_valid", "length"}:
                            return sqlite3.SQLITE_DENY
                        if action in {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE} and a not in {"sqlite_master", "sqlite_temp_master"}:
                            return sqlite3.SQLITE_DENY
                        return sqlite3.SQLITE_OK
                    db.set_authorizer(authorize)
                    db.set_progress_handler(lambda: 1, 100000)
                    db.executescript(sql)
            result.counts["executed"] += 1
        except (SyntaxError, ValueError, UnicodeError, sqlite3.Error) as exc:
            result.counts["executed"] += 1
            line = getattr(exc, "lineno", 1) or 1
            # Do not copy source lines or full SQL into the evidence store.
            message = getattr(exc, "msg", None) or str(exc)
            result.findings.append(finding(result, path=path, content_hash=snap.files[path]["hash"], rule=check_id, title=f"Invalid {check.category} input: {path}", actual=message, expected="Input must satisfy its parser's syntax and format contract", category=check.category, line=line, classification="check_failure" if isinstance(exc, sqlite3.Error) else "confirmed_defect"))
        except (RecursionError, MemoryError) as exc:
            result.outcome, result.completeness = "inconclusive", "partial"
            result.reasons.append(f"Parser resource limit: {path} ({type(exc).__name__})")
            result.counts["skipped"] += 1
    if result.findings and result.completeness == "complete":
        result.outcome = "failed"
    if snap.gaps:
        result.outcome = "inconclusive"
        result.completeness = "partial"
        result.reasons = (result.reasons + snap.gaps)[:100]
    return result
