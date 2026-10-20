from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath

from . import __version__
from .common import CompanionError, digest, identifier, now, redact

OUTCOMES = {"passed", "failed", "execution_error", "blocked", "skipped", "not_applicable", "inconclusive", "cancelled", "superseded"}


@dataclass(frozen=True)
class Check:
    check_id: str
    category: str
    description: str
    suffixes: tuple[str, ...]
    profile: str = "fast"
    version: str = __version__
    executable: bool = False

    def manifest(self) -> dict:
        return {"check_id": self.check_id, "version": self.version, "category": self.category, "description": self.description, "suffixes": list(self.suffixes), "profile": self.profile, "executable": self.executable}


@dataclass
class Result:
    check_id: str
    snapshot_id: str
    outcome: str
    completeness: str
    counts: dict
    run_id: str = field(default_factory=identifier)
    check_version: str = __version__
    exit_code: int | None = None
    findings: list[dict] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list, repr=False)
    verification_basis: dict = field(default_factory=dict, repr=False)

    def validate(self) -> None:
        if self.outcome not in OUTCOMES or self.completeness not in {"complete", "partial", "none"}:
            raise CompanionError("Invalid check outcome")
        if set(self.counts) != {"discovered", "executed", "skipped"}:
            raise CompanionError("Invalid count fields")
        for count in self.counts.values():
            if count is not None and (type(count) is not int or count < 0):
                raise CompanionError("Invalid check counts")
        discovered, executed, skipped = (self.counts[k] for k in ("discovered", "executed", "skipped"))
        if discovered is not None and executed is not None and skipped is not None and executed + skipped > discovered:
            raise CompanionError("Execution counts exceed discovery")
        if self.outcome == "passed" and (self.completeness != "complete" or not executed or not discovered or self.findings):
            raise CompanionError("A pass requires complete nonzero execution and no findings")
        if len(self.findings) > 1000 or len(self.reasons) > 100:
            raise CompanionError("Result exceeds contract bounds")
        for finding in self.findings:
            if finding["run_id"] != self.run_id or finding["snapshot_id"] != self.snapshot_id or finding["verification_check_ids"] != [self.check_id]:
                raise CompanionError("Finding/result identity mismatch")
            for location in finding["locations"]:
                path = PurePosixPath(location["path"])
                if path.is_absolute() or ".." in path.parts or "\\" in location["path"] or ":" in location["path"]:
                    raise CompanionError("Unsafe finding location")

    def json(self) -> dict:
        self.validate()
        return {"contract": "check_result", "schema_version": "1.0", "run_id": self.run_id, "snapshot_id": self.snapshot_id, "check_id": self.check_id, "check_version": self.check_version, "outcome": self.outcome, "completeness": self.completeness, "counts": self.counts, "exit_code": self.exit_code, "findings": self.findings, "reasons": self.reasons}


def finding(result: Result, *, path: str, content_hash: str, rule: str, title: str, actual: str, expected: str, category: str, line: int = 1, classification: str = "confirmed_defect", severity: str = "high") -> dict:
    fp = digest({"rule": rule, "path": path, "condition": title})
    return {"contract": "finding", "schema_version": "1.0", "finding_id": fp[:32], "fingerprint": fp, "rule_id": rule, "rule_version": __version__, "run_id": result.run_id, "snapshot_id": result.snapshot_id, "classification": classification, "category": category, "severity": severity, "confidence": "high", "title": redact(title)[:300], "expected": expected[:4000], "expected_basis": "Built-in language/file-format contract", "actual": redact(actual)[:4000], "locations": [{"path": path, "content_hash": content_hash, "line": max(1, line)}], "evidence": [], "reproduction": {"check_id": result.check_id, "instructions": f"Run companion check --check {result.check_id} on the saved project"}, "suggested_next_step": "Correct the reported input, preserve intended behavior, then verify this finding", "verification_check_ids": [result.check_id], "freshness": "current", "created_at": now()}
