"""Optional local ranking classifier; never trains an underlying provider model."""
from __future__ import annotations

import json
import math
import re
import time
from importlib.resources import files
from pathlib import Path

from . import __version__
from .common import CompanionError, atomic_write, canonical, digest, identifier, now, read_bounded, redact


def features(text):
    return [digest(word.lower().encode()) for word in re.findall(r"[A-Za-z][A-Za-z0-9_]{1,63}", redact(text))[:1000]]


def probability(model, text):
    scores = []
    vocabulary = max(1, len(model["vocabulary"]))
    for label in ("0", "1"):
        score = math.log((model["documents"][label] + 1) / (sum(model["documents"].values()) + 2))
        for token in features(text):
            score += math.log((model["counts"][label].get(token, 0) + 1) / (model["totals"][label] + vocabulary))
        scores.append(score)
    difference = max(-700, min(700, scores[1] - scores[0]))
    return 1 / (1 + math.exp(-difference))


def train(store, dataset_path: Path, authorized: bool):
    if not authorized:
        raise CompanionError("Local training is disabled by default; explicitly supply --authorize-local-training with a rights-cleared dataset")
    raw = read_bounded(dataset_path, 5 * 1024 * 1024)
    dataset_hash = digest(raw)
    data = json.loads(raw)
    authorization = data.get("authorization", {})
    if authorization.get("scope") != "local_project" or authorization.get("rights") != "authorized" or authorization.get("consent") is not True:
        raise CompanionError("Dataset needs explicit local-project rights and consent")
    samples = data.get("samples")
    if not isinstance(samples, list) or not 6 <= len(samples) <= 5000:
        raise CompanionError("Training needs 6–5000 explicit train/validation/test samples")
    train_samples, heldout, hashes, challenges = [], [], {}, set()
    for sample in samples:
        if not isinstance(sample, dict) or sample.get("split") not in {"train", "validation", "test"} or type(sample.get("label")) is not int or sample["label"] not in {0, 1} or not isinstance(sample.get("text"), str) or not 1 <= len(sample["text"]) <= 4000:
            raise CompanionError("Invalid labeled ranking sample")
        content_hash = digest(sample["text"].encode())
        if content_hash in hashes:
            raise CompanionError("Repeated content or cross-split leakage rejected")
        hashes[content_hash] = sample["split"]
        if sample.get("challenge_id"):
            cid = sample["challenge_id"]
            if not store.db.execute("SELECT 1 FROM challenges WHERE challenge_id=? AND state!='abandoned'", (cid,)).fetchone():
                raise CompanionError("Training lineage references unavailable challenge")
            challenges.add(cid)
        (train_samples if sample["split"] == "train" else heldout).append(sample)
    if {sample["label"] for sample in train_samples} != {0, 1} or {sample["split"] for sample in heldout} != {"validation", "test"}:
        raise CompanionError("Both training labels and independent validation/test splits are required")
    attempts = store.db.execute("SELECT count(*) FROM learned_artifacts WHERE json_extract(dataset_lineage_json,'$.dataset_hash')=?", (dataset_hash,)).fetchone()[0]
    if attempts >= 3:
        raise CompanionError("Evaluation budget exhausted for this dataset; supply independently held-out new evidence")
    started = time.monotonic()
    model = {"kind": "hashed_naive_bayes_ranking", "documents": {"0": 0, "1": 0}, "totals": {"0": 0, "1": 0}, "counts": {"0": {}, "1": {}}, "vocabulary": []}
    vocabulary = set()
    for sample in train_samples:
        label = str(sample["label"])
        model["documents"][label] += 1
        for token in features(sample["text"]):
            vocabulary.add(token)
            model["counts"][label][token] = model["counts"][label].get(token, 0) + 1
            model["totals"][label] += 1
        if len(vocabulary) > 20000 or time.monotonic() - started > 30:
            raise CompanionError("Local training resource budget exceeded")
    model["vocabulary"] = sorted(vocabulary)
    accuracies = {}
    for split in ("validation", "test"):
        cases = [sample for sample in heldout if sample["split"] == split]
        accuracies[split] = sum((probability(model, sample["text"]) >= 0.5) == bool(sample["label"]) for sample in cases) / len(cases)
    threshold = data.get("min_accuracy", 1.0)
    if type(threshold) not in (int, float) or not 0.5 <= threshold <= 1:
        raise CompanionError("Ranking acceptance threshold must be between 0.5 and 1")
    passed = all(value >= threshold for value in accuracies.values())
    artifact_id, learned_id, candidate_id = identifier(), identifier(), identifier()
    evaluator_hash = digest(files("coding_companion").joinpath("learning.py").read_bytes())
    body = canonical(model).encode()
    relative = f"learned/{learned_id}.json"
    atomic_write(store.state / relative, body)
    proposal = {"kind": "trained_component", "artifact_sha256": digest(body), "dataset_hash": dataset_hash, "algorithm": model["kind"]}
    metrics = {"passed": passed, "accuracies": accuracies, "min_accuracy": threshold, "heldout_samples": len(heldout), "duration_ms": int((time.monotonic() - started) * 1000), "use": "Optional ranking only; required checks cannot be suppressed"}
    with store.transaction():
        store.insert("artifacts", artifact_id=artifact_id, relative_state_path=relative, media_type="application/json", sha256=digest(body), size_bytes=len(body), redaction_state="sanitized", created_at=now(), state="available")
        store.insert("improvement_candidates", candidate_id=candidate_id, kind="trained_component", base_version=__version__, base_package_sha256=digest({"version": __version__, "evaluator": evaluator_hash}), proposed_hash=digest(proposal), evaluator_sha256=evaluator_hash, heldout_fixture_sha256=digest([{key: sample[key] for key in ("text", "label", "split")} for sample in heldout]), proposal_json=canonical(proposal), evaluation_json=canonical(metrics), state="evaluated" if passed else "rejected", evaluation_passed=int(passed), approval_json="{}", created_at=now())
        store.insert("learned_artifacts", learned_artifact_id=learned_id, candidate_id=candidate_id, artifact_id=artifact_id, version=__version__, dataset_lineage_json=canonical({"dataset_hash": dataset_hash, "dataset_path": str(dataset_path.resolve()), "challenge_ids": sorted(challenges), "sample_hashes": sorted(hashes)}), authorization_json=canonical({"scope": "local_project", "rights": "authorized", "consent": True, "explicit_cli_authorization": True}), evaluation_json=canonical(metrics), state="candidate", created_at=now())
    return {"status": "evaluated" if passed else "rejected", "learned_artifact_id": learned_id, "candidate_id": candidate_id, "metrics": metrics}


def manage(store, action, learned_id=None, text=None, approve=False):
    if action == "list":
        return {"artifacts": [dict(r) for r in store.db.execute("SELECT learned_artifact_id,candidate_id,state,evaluation_json FROM learned_artifacts ORDER BY created_at DESC LIMIT 100")]}
    row = store.db.execute("SELECT l.*,a.relative_state_path,a.sha256,a.state artifact_state,c.evaluator_sha256,c.evaluation_passed,c.proposed_hash FROM learned_artifacts l JOIN artifacts a ON a.artifact_id=l.artifact_id JOIN improvement_candidates c ON c.candidate_id=l.candidate_id WHERE l.learned_artifact_id=?", (learned_id,)).fetchone()
    if not row:
        raise CompanionError("Unknown learned artifact")
    if action == "revoke":
        with store.transaction():
            store.db.execute("UPDATE learned_artifacts SET state='deleted' WHERE learned_artifact_id=?", (learned_id,))
            store.db.execute("UPDATE improvement_candidates SET state='rolled_back' WHERE candidate_id=?", (row["candidate_id"],))
            store.db.execute("UPDATE artifacts SET state='quarantined' WHERE artifact_id=?", (row["artifact_id"],))
        from .maintenance import purge_files
        return {"status": "revoked", "cleanup": purge_files(store)}
    lineage = json.loads(row["dataset_lineage_json"])
    if row["artifact_state"] != "available" or row["state"] in {"deleted", "disabled", "rolled_back"}:
        raise CompanionError("Learned artifact is unavailable or withdrawn")
    if digest(files("coding_companion").joinpath("learning.py").read_bytes()) != row["evaluator_sha256"]:
        raise CompanionError("Ranking evaluator changed; reevaluate/retrain before use")
    if digest(read_bounded(Path(lineage["dataset_path"]), 5 * 1024 * 1024)) != lineage["dataset_hash"]:
        raise CompanionError("Dataset authorization/lineage changed; retrain from currently authorized data")
    path = store.state / row["relative_state_path"]
    data = read_bounded(path, 10 * 1024 * 1024)
    if digest(data) != row["sha256"]:
        raise CompanionError("Learned artifact bytes changed")
    if action == "activate":
        if not approve or not row["evaluation_passed"] or row["state"] != "candidate" or digest(files("coding_companion").joinpath("learning.py").read_bytes()) != row["evaluator_sha256"]:
            raise CompanionError("Activation requires reviewed current evaluator, passed evaluation and --approve")
        with store.transaction():
            store.db.execute("UPDATE learned_artifacts SET state='active' WHERE learned_artifact_id=?", (learned_id,))
            store.db.execute("UPDATE improvement_candidates SET state='active',activated_at=?,approval_json=? WHERE candidate_id=?", (now(), canonical({"actor": "user", "proposed_hash": row["proposed_hash"]}), row["candidate_id"]))
        return {"status": "active", "learned_artifact_id": learned_id}
    if action != "score" or row["state"] != "active" or not isinstance(text, str) or len(text) > 4000:
        raise CompanionError("Scoring requires an active artifact and bounded text")
    return {"probability": probability(json.loads(data), text), "scope": "Optional ranking evidence only", "required_checks_unchanged": True}
