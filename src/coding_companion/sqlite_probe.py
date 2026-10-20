"""Read-only customer SQLite backup, integrity, relations and scalar contracts."""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
import xml.etree.ElementTree as ET
from contextlib import closing
from pathlib import Path


def run(source, report, contract=None):
    if not source.is_file() or source.is_symlink() or source.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("SQLite input must be an unlinked bounded local file")
    cases = []
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)) as original, closing(sqlite3.connect(":memory:")) as database:
        deadline = time.monotonic() + 30
        def progress(status, remaining, total):
            if time.monotonic() > deadline:
                raise TimeoutError("Database snapshot budget exceeded")
        original.backup(database, pages=256, progress=progress)
        database.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        integrity = database.execute("PRAGMA integrity_check").fetchmany(1001)
        foreign = database.execute("PRAGMA foreign_key_check").fetchmany(1001)
        for name, passed in (("integrity", integrity == [("ok",)]), ("foreign_keys", not foreign)):
            case = ET.Element("testcase", name=name)
            if not passed:
                ET.SubElement(case, "failure", message="SQLite state violates its declared integrity/relation constraint")
            cases.append(case)
        queries = (contract or {}).get("queries", [])
        if not isinstance(queries, list) or len(queries) > 100:
            raise ValueError("Scalar query contract budget exceeded")
        denied = {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_PRAGMA, sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE, sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_DROP_TABLE, sqlite3.SQLITE_ALTER_TABLE}
        def authorize(action, a, b, c, d):
            if action in denied or (action == sqlite3.SQLITE_FUNCTION and b not in {"count", "sum", "avg", "min", "max", "length", "abs", "coalesce", "round"}):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        database.set_authorizer(authorize)
        for i, query in enumerate(queries):
            case = ET.Element("testcase", name=str(query.get("id", f"scalar-{i}")))
            try:
                if not isinstance(query.get("sql"), str) or len(query["sql"]) > 5000 or "equals" not in query:
                    raise ValueError("Explicit bounded scalar query expectation required")
                result = database.execute(query["sql"]).fetchmany(2)
                if len(result) != 1 or len(result[0]) != 1 or result[0][0] != query["equals"]:
                    ET.SubElement(case, "failure", message="Declared scalar database acceptance contract failed")
            except Exception as error:
                ET.SubElement(case, "error", message=type(error).__name__)
            cases.append(case)
    suite = ET.Element("testsuite", tests=str(len(cases)), failures=str(sum(c.find("failure") is not None for c in cases)), errors=str(sum(c.find("error") is not None for c in cases)))
    suite.extend(cases)
    report.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite).write(report, encoding="utf-8", xml_declaration=True)
    return 1 if any(c.find("failure") is not None or c.find("error") is not None for c in cases) else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.contract:
        with args.contract.open("rb") as handle:
            raw = handle.read(1024 * 1024 + 1)
    else:
        raw = b"{}"
    if len(raw) > 1024 * 1024:
        raise ValueError("Database contract byte limit exceeded")
    raise SystemExit(run(args.database, args.report, json.loads(raw)))
