"""Validate requirement evidence references without claiming runtime certification."""
from __future__ import annotations

import argparse
import ast
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def requirement_inventory(root):
    text = (root / "COMPANION_REQUIREMENTS.md").read_text(encoding="utf-8")
    result = dict(re.findall(r"^- ([A-Z]\d{2}): (.+)$", text, re.M))
    result.update(re.findall(r"^### (C\d{2}) — (.+)$", text, re.M))
    return result


def validate_ledger(document, root=ROOT):
    inventory = requirement_inventory(root)
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("Requirement ledger schema_version must be 1")
    entries = document.get("requirements")
    if not isinstance(entries, list):
        raise ValueError("requirements must be an array")
    seen, counts, symbol_cache = set(), Counter(), {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Requirement entry must be an object")
        identifier, status = entry.get("id"), entry.get("status")
        if identifier not in inventory or identifier in seen:
            raise ValueError(f"Unknown or duplicate requirement: {identifier}")
        seen.add(identifier)
        if entry.get("requirement") != inventory[identifier]:
            raise ValueError(f"Requirement wording drift: {identifier}")
        if status not in {"implemented", "partial", "deferred", "unassessed"}:
            raise ValueError(f"Invalid status: {identifier}")
        counts[status] += 1
        sources, tests, missing = (entry.get(key) for key in ("sources", "tests", "remaining"))
        if any(not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value) for value in (sources, tests, missing)):
            raise ValueError(f"Invalid evidence arrays: {identifier}")
        if status == "implemented" and (not sources or not tests or missing):
            raise ValueError(f"Implemented requirement needs source/test evidence and no remaining gates: {identifier}")
        if status != "implemented" and not missing:
            raise ValueError(f"Incomplete requirement needs explicit remaining gates: {identifier}")
        for reference in sources + tests:
            relative, separator, symbol = reference.partition("::")
            path = root / relative
            if "\\" in relative or Path(relative).is_absolute() or ".." in Path(relative).parts or not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
                raise ValueError(f"Invalid evidence path: {reference}")
            if relative.startswith(("design/", "dist/")) and status == "implemented":
                raise ValueError(f"Design/generated records cannot certify implementation: {identifier}")
            if separator:
                if path.suffix != ".py":
                    raise ValueError(f"Symbol reference must point to Python: {reference}")
                if relative not in symbol_cache:
                    tree = ast.parse(path.read_text(encoding="utf-8"))
                    symbols = set()
                    def collect(nodes, prefix=""):
                        for node in nodes:
                            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                                name = prefix + node.name
                                symbols.add(name)
                                collect(node.body, name + ".")
                    collect(tree.body)
                    symbol_cache[relative] = symbols
                symbols = symbol_cache[relative]
                if symbol not in symbols:
                    raise ValueError(f"Missing evidence symbol: {reference}")
            if reference in tests and (not relative.startswith("tests/") or not separator or not symbol.split(".")[-1].startswith("test_")):
                raise ValueError(f"Test evidence needs a concrete test function: {reference}")
    if seen != set(inventory):
        raise ValueError(f"Missing requirements: {sorted(set(inventory) - seen)}")
    return {"status": "passed", "requirements": len(seen), "counts": dict(sorted(counts.items())), "scope": "Evidence references and completion gates only; test execution and semantic review remain separate"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=ROOT / "design/requirements.json")
    args = parser.parse_args()
    print(json.dumps(validate_ledger(json.loads(args.ledger.read_text(encoding="utf-8"))), indent=2))


if __name__ == "__main__":
    main()
