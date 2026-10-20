"""Deterministic packs over explicit local contracts and captured evidence."""
from __future__ import annotations

import ast
import csv
import io
import json
import math
from html.parser import HTMLParser
from pathlib import PurePosixPath

from .common import CompanionError, digest, strict_json
from .contracts import Check, Result, finding

PACK_CHECKS = {
    "security.patterns": Check("security.patterns", "security", "Inspect Python dangerous-call patterns; findings are predicted risks", (".py",)),
    "web.semantics": Check("web.semantics", "accessibility", "Inspect local HTML alternative text and duplicate IDs; rendered behavior remains unchecked", (".html", ".htm")),
    "data.contracts": Check("data.contracts", "data", "Validate explicit local data contracts without persisting row values", (".json",)),
    "rag.contracts": Check("rag.contracts", "rag", "Validate captured retrieval/index tenant, deletion, version and relevance contracts", (".json",)),
    "ai.contracts": Check("ai.contracts", "model", "Validate captured structured responses, grounding IDs and declared expectations", (".json",)),
    "model.contracts": Check("model.contracts", "model", "Validate declared model identity, context budget and local artifact hashes", (".json",)),
    "training.contracts": Check("training.contracts", "training", "Validate declared dataset rights, split isolation and finite loss records", (".json",)),
    "performance.contracts": Check("performance.contracts", "performance", "Validate supplied measured latency samples against explicit workload/thresholds", (".json",)),
}
MANIFEST_NAMES = {"data.contracts": "companion.data.json", "rag.contracts": "companion.rag.json", "ai.contracts": "companion.evals.json", "model.contracts": "companion.model.json", "training.contracts": "companion.training.json", "performance.contracts": "companion.metrics.json"}


def paths_for(check_id, snap):
    check = PACK_CHECKS[check_id]
    return [p for p in snap.files if PurePosixPath(p).suffix in check.suffixes and (check_id not in MANIFEST_NAMES or PurePosixPath(p).name == MANIFEST_NAMES[check_id])]


class Semantics(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.issues, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "img" and "alt" not in attrs:
            self.issues.append(("missing-alt", "Image has no alt attribute", self.getpos()[0]))
        if attrs.get("id"):
            if attrs["id"] in self.ids:
                self.issues.append(("duplicate-id", "Document contains a duplicate element ID", self.getpos()[0]))
            self.ids.add(attrs["id"])


def require(condition, message):
    if not condition:
        raise CompanionError(message)


def local_path(value, snap):
    require(isinstance(value, str), "Data path must be a string")
    path = PurePosixPath(value)
    require(not path.is_absolute() and ".." not in path.parts and "\\" not in value and ":" not in value and value in snap.contents, "Data input is outside bounded discovered coverage")
    return value


def rows(path, snap):
    text = snap.contents[path].decode("utf-8-sig")
    if path.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(text))
        result = []
        for row in reader:
            require(len(result) < 100000, "Dataset row bound exceeded")
            result.append(row)
    elif path.endswith(".jsonl"):
        lines = text.splitlines()
        require(len(lines) <= 100000, "Dataset row bound exceeded")
        result = [json.loads(line) for line in lines if line.strip()]
    else:
        result = json.loads(text)
    require(isinstance(result, list) and len(result) <= 100000 and all(isinstance(row, dict) for row in result), "Dataset must be a bounded array of objects")
    return result


def validate_manifest(check_id, data, snap):
    require(isinstance(data, dict), "Contract must be an object")
    issues = []
    def issue(rule, condition, message):
        if not condition:
            issues.append((rule, message, 1))
    if check_id == "data.contracts":
        datasets = data.get("datasets")
        require(isinstance(datasets, list) and 0 < len(datasets) <= 100, "Data contract needs 1–100 datasets")
        loaded = {}
        for index, spec in enumerate(datasets):
            require(isinstance(spec, dict), "Dataset contract must be an object")
            path = local_path(spec.get("path"), snap)
            dataset = rows(path, snap)
            loaded[path] = dataset
            issue(f"rows-{index}", len(dataset) >= spec.get("min_rows", 1), "Dataset has fewer rows than the declared minimum")
            if "expected_rows" in spec:
                issue(f"count-{index}", len(dataset) == spec["expected_rows"], "Dataset row count contradicts the declared count")
            required = spec.get("required_fields", [])
            require(isinstance(required, list) and all(isinstance(key, str) for key in required), "Required fields must be names")
            issue(f"fields-{index}", all(all(key in row and row[key] not in (None, "") for key in required) for row in dataset), "Dataset contains absent or null required fields")
            keys = spec.get("unique_by", [])
            require(isinstance(keys, list) and all(isinstance(key, str) for key in keys), "Unique keys must be names")
            if keys:
                fingerprints = [digest([row.get(key) for key in keys]) for row in dataset]
                issue(f"unique-{index}", len(set(fingerprints)) == len(fingerprints), "Dataset violates the declared uniqueness contract")
        for index, relation in enumerate(data.get("relations", [])):
            require(isinstance(relation, dict), "Relation must be an object")
            source, target = relation.get("source"), relation.get("target")
            require(source in loaded and target in loaded, "Relation references an undeclared dataset")
            expected = {digest(row.get(relation["target_key"])) for row in loaded[target]}
            issue(f"relation-{index}", all(digest(row.get(relation["source_key"])) in expected for row in loaded[source]), "Dataset contains an orphan relation")
    elif check_id == "rag.contracts":
        docs, index = data.get("documents"), data.get("index")
        require(isinstance(docs, list) and isinstance(index, list) and len(docs) <= 10000 and len(index) <= 10000, "RAG contract needs bounded documents and index arrays")
        ids = {d["id"]: d for d in docs}
        require(all(isinstance(d.get("id"), str) and d["id"] and d.get("tenant") is not None and d.get("version") is not None for d in docs), "Documents require identity, tenant and version")
        issue("document-ids", len(ids) == len(docs), "Document IDs are duplicated")
        require(type(data.get("embedding_dimension")) is int and data["embedding_dimension"] > 0, "Embedding dimension required")
        for i, entry in enumerate(index):
            doc = ids.get(entry.get("document_id"))
            issue(f"index-{i}", doc is not None and not doc.get("deleted", False) and entry.get("version") == doc.get("version") and entry.get("tenant") == doc.get("tenant") and entry.get("dimension") == data["embedding_dimension"], "Index entry is missing, deleted, stale, tenant-mismatched or dimension-incompatible")
        queries = data.get("queries", [])
        require(isinstance(queries, list) and 0 < len(queries) <= 1000, "Captured retrieval queries required")
        for i, query in enumerate(queries):
            retrieved = query.get("retrieved_document_ids", [])
            relevant = set(query.get("relevant_document_ids", []))
            require(isinstance(retrieved, list) and relevant, "Captured query needs retrieval IDs and an explicit relevant set")
            issue(f"isolation-{i}", all(doc_id in ids and not ids[doc_id].get("deleted", False) and ids[doc_id].get("tenant") == query.get("tenant") for doc_id in retrieved), "Captured retrieval leaks tenant/deleted/unknown documents")
            recall = len(set(retrieved).intersection(relevant)) / len(relevant)
            issue(f"recall-{i}", recall >= query.get("min_recall", 1.0), "Captured retrieval recall falls below its declared threshold")
    elif check_id == "ai.contracts":
        cases = data.get("cases")
        require(isinstance(cases, list) and 0 < len(cases) <= 1000, "Captured AI evaluation cases required")
        for i, case in enumerate(cases):
            require(isinstance(case, dict) and "actual" in case and "expected" in case, "AI cases require actual and expected evidence")
            actual, expected = case["actual"], case["expected"]
            require(isinstance(expected, dict), "Expected output must declare its contract")
            require(set(expected) <= {"exact", "required_fields", "allowed_citation_ids", "forbidden_substrings"}, "Unknown AI acceptance assertion")
            require("exact" in expected or bool(expected.get("required_fields")) or "allowed_citation_ids" in expected or bool(expected.get("forbidden_substrings")), "AI case has no meaningful acceptance assertion")
            if "exact" in expected:
                issue(f"exact-{i}", actual == expected["exact"], "Captured response contradicts the declared exact expectation")
            if "required_fields" in expected:
                issue(f"structure-{i}", isinstance(actual, dict) and all(k in actual for k in expected["required_fields"]), "Captured structured response misses required fields")
            if "allowed_citation_ids" in expected:
                issue(f"grounding-{i}", isinstance(actual, dict) and set(actual.get("citations", [])).issubset(set(expected["allowed_citation_ids"])), "Captured response cites unauthorized or unknown evidence")
            serialized = json.dumps(actual, ensure_ascii=True)
            issue(f"leakage-{i}", all(value not in serialized for value in expected.get("forbidden_substrings", [])), "Captured response contains declared forbidden content")
            require(bool(expected), "AI case has no acceptance assertion")
    elif check_id == "model.contracts":
        require(all(isinstance(data.get(key), str) and data[key] for key in ("model_id", "revision", "license", "tokenizer")), "Model identity/revision/license/tokenizer are required")
        require(type(data.get("context_limit")) is int and data["context_limit"] > 0, "Positive model context limit required")
        require(all(type(data.get(k, 0)) is int and data.get(k, 0) >= 0 for k in ("prompt_tokens", "max_new_tokens")), "Token budgets must be nonnegative integers")
        issue("context", data.get("prompt_tokens", 0) + data.get("max_new_tokens", 0) <= data["context_limit"], "Declared generation exceeds model context capacity")
        issue("remote-code", data.get("trust_remote_code", False) is False, "Remote code loading requires a separate reviewed execution boundary")
        for i, artifact in enumerate(data.get("artifacts", [])):
            path = local_path(artifact.get("path"), snap)
            issue(f"artifact-{i}", snap.files[path]["hash"] == artifact.get("sha256"), "Local model artifact hash differs from declared provenance")
    elif check_id == "training.contracts":
        samples = data.get("samples")
        require(isinstance(samples, list) and 0 < len(samples) <= 100000, "Training samples/lineage are required")
        identities = {}
        for sample in samples:
            require(isinstance(sample, dict) and sample.get("split") in {"train", "validation", "test"} and isinstance(sample.get("content_hash"), str), "Sample identity/split is missing")
            identities.setdefault(sample["content_hash"], set()).add(sample["split"])
        issue("rights", all(sample.get("rights") == "authorized" and sample.get("consent") is True for sample in samples), "Dataset includes samples without declared rights and consent")
        issue("split-leakage", all(len(splits) == 1 for splits in identities.values()), "Training and held-out splits share sample content")
        losses = data.get("losses", [])
        require(isinstance(losses, list) and losses, "Captured finite loss values required")
        issue("finite-loss", all(type(value) in (int, float) and math.isfinite(value) for value in losses), "Captured training loss is nonfinite or invalid")
        require(type(data.get("seed")) is int, "Training reproducibility seed required")
    elif check_id == "performance.contracts":
        require(isinstance(data.get("workload"), dict) and data["workload"].get("concurrency", 0) > 0 and data["workload"].get("duration_seconds", 0) > 0 and data.get("captured_revision"), "Measured workload, duration, concurrency and revision required")
        samples = data.get("latency_ms")
        require(isinstance(samples, list) and 0 < len(samples) <= 100000 and all(type(x) in (int, float) and math.isfinite(x) and x >= 0 for x in samples), "Bounded finite measured latency samples required")
        thresholds = data.get("thresholds")
        require(isinstance(thresholds, dict) and "p95_ms" in thresholds, "Explicit p95 threshold required")
        ordered = sorted(samples)
        require(type(data.get("errors", 0)) is int and 0 <= data.get("errors", 0) <= len(samples), "Measured error count is invalid")
        require(type(thresholds["p95_ms"]) in (int, float) and math.isfinite(thresholds["p95_ms"]) and thresholds["p95_ms"] >= 0 and 0 <= thresholds.get("max_error_rate", 0) <= 1, "Performance threshold is invalid")
        p95 = ordered[max(0, math.ceil(0.95 * len(samples)) - 1)]
        issue("p95", p95 <= thresholds["p95_ms"], "Measured p95 latency exceeds the declared workload threshold")
        issue("errors", data.get("errors", 0) / len(samples) <= thresholds.get("max_error_rate", 0), "Measured error rate exceeds its declared threshold")
    return issues[:1000]


def acceptance_signature(check_id, data):
    if check_id == "ai.contracts":
        projected = [{"id": c.get("id"), "input_hash": c.get("input_hash"), "expected": c.get("expected")} for c in data.get("cases", [])]
    elif check_id == "performance.contracts":
        projected = {"workload": data.get("workload"), "thresholds": data.get("thresholds")}
    elif check_id == "rag.contracts":
        projected = {"dimension": data.get("embedding_dimension"), "documents": data.get("documents"), "queries": [{key: value for key, value in query.items() if key != "retrieved_document_ids"} for query in data.get("queries", [])]}
    elif check_id == "model.contracts":
        projected = {key: value for key, value in data.items() if key not in {"prompt_tokens", "max_new_tokens", "trust_remote_code"}}
    elif check_id == "training.contracts":
        projected = {"rule": "authorized_disjoint_splits_finite_loss", "seed": data.get("seed")}
    else:
        projected = data
    return digest(projected)


def run_pack(check_id, snap, run_id=None):
    paths = paths_for(check_id, snap)
    result = Result(check_id, snap.snapshot_id, "passed", "complete", {"discovered": len(paths), "executed": 0, "skipped": 0})
    if run_id:
        result.run_id = run_id
    if not paths:
        result.outcome, result.completeness, result.reasons = "not_applicable", "none", ["No explicit applicable contract/input"]
        return result
    for path in paths:
        try:
            if check_id == "security.patterns":
                tree = ast.parse(snap.contents[path])
                issues = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                            issues.append((node.func.id, "Dynamic code execution requires reviewed input provenance", node.lineno))
                        if any(k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords):
                            issues.append(("shell", "Shell execution requires reviewed argument/input provenance", node.lineno))
                issues = list({rule: (rule, message, line) for rule, message, line in issues}.values())
            elif check_id == "web.semantics":
                parser = Semantics()
                parser.feed(snap.contents[path].decode("utf-8-sig"))
                issues = list({rule: (rule, message, line) for rule, message, line in parser.issues}.values())
            else:
                data = strict_json(snap.contents[path])
                issues = validate_manifest(check_id, data, snap)
                result.verification_basis.setdefault("acceptance_hashes", {})[path] = acceptance_signature(check_id, data)
            result.counts["executed"] += 1
            for rule, message, line in issues:
                if len(result.findings) == 1000:
                    result.completeness, result.outcome = "partial", "inconclusive"
                    break
                item = finding(result, path=path, content_hash=snap.files[path]["hash"], rule=check_id + "." + rule, title=message, actual="Local input/captured evidence violates this explicitly selected rule", expected="Input satisfies its declared local acceptance contract", category=PACK_CHECKS[check_id].category, line=line, classification="predicted_risk" if check_id in {"security.patterns", "web.semantics"} else "confirmed_defect", severity="medium")
                item["expected_basis"] = "Explicit local acceptance contract in " + path if check_id in MANIFEST_NAMES else "Selected heuristic rule; this is a predicted risk rather than proof of application failure"
                result.findings.append(item)
        except (ValueError, TypeError, KeyError, UnicodeError, CompanionError, SyntaxError, csv.Error) as exc:
            result.counts["skipped"] += 1
            result.outcome, result.completeness = "execution_error", "partial"
            result.reasons.append(f"Contract evidence could not be evaluated: {path} ({type(exc).__name__})")
    if result.findings and result.completeness == "complete":
        result.outcome = "failed"
    if snap.gaps:
        result.outcome, result.completeness = "inconclusive", "partial"
        result.reasons = (result.reasons + snap.gaps)[:100]
    return result
