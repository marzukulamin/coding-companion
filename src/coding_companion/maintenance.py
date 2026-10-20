from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .common import CompanionError, atomic_write, canonical, digest, file_digest, identifier, inside, now, read_bounded, redact


def suppress(store, finding_id: str, reason: str, expires_at: str | None = None):
    item = store.inspect(finding_id)
    if not reason or len(reason) > 2000:
        raise CompanionError("Suppression requires a bounded reason")
    if expires_at:
        date = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if date.tzinfo is None or date <= datetime.now(timezone.utc):
            raise CompanionError("Suppression expiry must be a future timezone-aware timestamp")
        expires_at = date.isoformat().replace("+00:00", "Z")
    sid = identifier()
    with store.transaction():
        store.insert("suppressions", suppression_id=sid, finding_id=finding_id, scope_json=canonical({"project_id": store.project_id, "previous_lifecycle": item["lifecycle"]}), reason=redact(reason), created_at=now(), expires_at=expires_at)
        store.db.execute("UPDATE findings SET lifecycle='accepted_risk' WHERE finding_id=?", (finding_id,))
        store.audit("suppress", "finding", finding_id)
    return {"suppression_id": sid, "finding_id": finding_id, "expires_at": expires_at}


def unsuppress(store, suppression_id: str):
    row = store.db.execute("SELECT * FROM suppressions WHERE suppression_id=?", (suppression_id,)).fetchone()
    if not row:
        raise CompanionError("Unknown suppression")
    with store.transaction():
        store.db.execute("DELETE FROM suppressions WHERE suppression_id=?", (suppression_id,))
        others = store.db.execute("SELECT 1 FROM suppressions WHERE finding_id=? AND (expires_at IS NULL OR expires_at>?)", (row["finding_id"], now())).fetchone()
        if not others:
            previous = json.loads(row["scope_json"]).get("previous_lifecycle", "acknowledged")
            if previous == "accepted_risk":
                previous = "acknowledged"
            store.db.execute("UPDATE findings SET lifecycle=? WHERE finding_id=? AND lifecycle='accepted_risk'", (previous, row["finding_id"]))
        store.audit("unsuppress", "finding", row["finding_id"])


def withdraw(store, kind: str, entity_id: str) -> dict:
    if kind not in {"lesson", "challenge", "finding"}:
        raise CompanionError("Unsupported deletion entity")
    table = {"lesson": "lessons", "challenge": "challenges", "finding": "findings"}[kind]
    if not store.db.execute(f"SELECT 1 FROM {table} WHERE {kind}_id=?", (entity_id,)).fetchone():
        raise CompanionError("Unknown deletion entity")
    deletion = identifier()
    from .mailbox import privacy_epoch
    epoch = privacy_epoch(store.state) + 1
    marker = {"epoch": epoch, "created_at": now(), "deletion_id": deletion, "pending": True}
    with store.transaction():
        store.insert("deletion_records", deletion_id=deletion, entity_type=kind, entity_id=entity_id, state="tombstoned", created_at=now())
        lesson_ids = {entity_id} if kind == "lesson" else set()
        challenge_ids = {entity_id} if kind == "challenge" else set()
        if kind == "finding":
            challenge_ids.update(row[0] for row in store.db.execute("SELECT challenge_id FROM challenges WHERE finding_id=?", (entity_id,)))
            lesson_ids.update(row[0] for row in store.db.execute("SELECT lesson_id FROM lessons WHERE json_extract(evidence_json,'$.finding_id')=?", (entity_id,)))
        for cid in challenge_ids:
            lesson_ids.update(row[0] for row in store.db.execute("SELECT lesson_id FROM lessons WHERE challenge_id=?", (cid,)))
            store.db.execute("UPDATE challenges SET goal='',symptoms='',constraints_json='{}',attempts_json='[]',hypotheses_json='[]',provenance_json='{}',evidence_json='[]',state='abandoned',resolution=NULL,verification_run_id=NULL,updated_at=? WHERE challenge_id=?", (now(), cid))
        candidates = set()
        for lid in lesson_ids:
            candidates.update(row[0] for row in store.db.execute("SELECT candidate_id FROM improvement_candidates WHERE json_extract(approval_json,'$.lesson_id')=?", (lid,)))
            store.db.execute("UPDATE lessons SET status='revoked',summary='',tags='',evidence_json='{}',provenance_json='{}',applicability_json='{}' WHERE lesson_id=?", (lid,))
        if kind == "finding":
            candidates.update(row[0] for row in store.db.execute("SELECT candidate_id FROM improvement_candidates WHERE json_extract(proposal_json,'$.finding_id')=?", (entity_id,)))
        for cid in challenge_ids:
            candidates.update(row[0] for row in store.db.execute("SELECT candidate_id FROM improvement_candidates WHERE challenge_id=?", (cid,)))
            candidates.update(row[0] for row in store.db.execute("SELECT candidate_id FROM learned_artifacts WHERE EXISTS (SELECT 1 FROM json_each(learned_artifacts.dataset_lineage_json,'$.challenge_ids') WHERE value=?)", (cid,)))
        for cid in candidates:
            store.db.execute("UPDATE learned_artifacts SET state='deleted',dataset_lineage_json='{}',authorization_json='{}',evaluation_json='{}' WHERE candidate_id=?", (cid,))
            store.db.execute("UPDATE artifacts SET state='quarantined' WHERE artifact_id IN (SELECT artifact_id FROM learned_artifacts WHERE candidate_id=?)", (cid,))
            store.db.execute("UPDATE improvement_candidates SET state='rolled_back',proposal_json='{}',evaluation_json='{}',approval_json='{}' WHERE candidate_id=?", (cid,))
        if kind == "finding":
            run_ids = {row[0] for row in store.db.execute("SELECT run_id FROM observations WHERE finding_id=?", (entity_id,))}
            store.db.execute("UPDATE artifacts SET state='quarantined' WHERE artifact_id IN (SELECT a.artifact_id FROM observation_artifacts a JOIN observations o ON o.observation_id=a.observation_id WHERE o.finding_id=?)", (entity_id,))
            store.db.execute("DELETE FROM observation_artifacts WHERE observation_id IN (SELECT observation_id FROM observations WHERE finding_id=?)", (entity_id,))
            store.db.execute("DELETE FROM deliveries WHERE finding_id=?", (entity_id,))
            store.db.execute("DELETE FROM observations WHERE finding_id=?", (entity_id,))
            store.db.execute("DELETE FROM suppressions WHERE finding_id=?", (entity_id,))
            store.db.execute("UPDATE challenges SET finding_id=NULL WHERE finding_id=?", (entity_id,))
            store.db.execute("DELETE FROM findings WHERE finding_id=?", (entity_id,))
            for rid in run_ids:
                result = json.loads(store.db.execute("SELECT result_json FROM runs WHERE run_id=?", (rid,)).fetchone()[0])
                result["findings"] = [f for f in result.get("findings", []) if f["finding_id"] != entity_id]
                result.update(outcome="inconclusive", completeness="partial", reasons=["Evidence withdrawn"])
                store.db.execute("UPDATE runs SET outcome='inconclusive',completeness='partial',result_json=? WHERE run_id=?", (canonical(result), rid))
        # All registered exports are conservatively withdrawn. External copies are
        # reported, not silently deleted outside the state root.
        store.db.execute("UPDATE exports SET state='withdrawn' WHERE state='available'")
        # Durable query/replay caches may contain excerpts of withdrawn lessons.
        # Keep request provenance hashes, but remove cached payloads and responses.
        store.db.execute("UPDATE events SET payload_json='{}',state='expired',result_json=json_object('status','expired','completeness','none','request_id',request_id,'reasons',json_array('Diagnostic history withdrawn')) WHERE state IN ('processed','expired','rejected')")
        store.db.execute("UPDATE events SET payload_json='{}',state='expired',result_json=json_object('status','expired','completeness','none','request_id',request_id,'reasons',json_array('Privacy-sensitive queued request withdrawn')) WHERE state='queued' AND (json_extract(payload_json,'$.operation')='memory_search' OR json_extract(payload_json,'$.args.lesson') IS NOT NULL)")
        store.audit("withdraw", kind, entity_id)
        atomic_write(store.state / "privacy-epoch.json", canonical(marker).encode())
    marker["pending"] = False
    atomic_write(store.state / "privacy-epoch.json", canonical(marker).encode())
    for path in sorted((store.state / "responses").glob("*.json"))[:100]:
        if not path.is_symlink():
            path.unlink()
    cleanup = purge_files(store)
    with store.transaction():
        store.db.execute("UPDATE deletion_records SET state='scrubbed',completed_at=? WHERE deletion_id=?", (now(), deletion))
    return {"status": "deleted", "deletion_id": deletion, "invalidated_lessons": len(lesson_ids), "retired_candidates": len(candidates), "cleanup": cleanup, "external_copy_note": "Registered exports marked withdrawn; separately remove external copies/backups. Secure SSD erasure and model unlearning are not claimed."}


def purge_files(store, limit=100) -> dict:
    removed, blocked = [], []
    for row in store.db.execute("SELECT artifact_id,relative_state_path FROM artifacts WHERE state IN ('expired','quarantined','missing') LIMIT ?", (limit,)).fetchall():
        path = store.state / row["relative_state_path"]
        try:
            inside(store.state, path)
            if path.is_symlink() or path.is_junction():
                raise CompanionError("Linked artifact rejected")
            if path.exists():
                path.unlink()
            store.db.execute("UPDATE artifacts SET state='missing' WHERE artifact_id=?", (row["artifact_id"],))
            removed.append(row["artifact_id"])
        except (OSError, CompanionError):
            blocked.append(row["artifact_id"])
    exports = []
    for row in store.db.execute("SELECT * FROM exports WHERE state='withdrawn' LIMIT ?", (limit,)).fetchall():
        path = Path(row["absolute_path"])
        if not path.resolve().is_relative_to(store.state.resolve()):
            exports.append({"export_id": row["export_id"], "state": "external_removal_required"})
            continue
        try:
            inside(store.state, path)
            if path.exists() and file_digest(path, store.config.max_state_bytes) != row["sha256"]:
                store.db.execute("UPDATE exports SET state='modified' WHERE export_id=?", (row["export_id"],))
                exports.append({"export_id": row["export_id"], "state": "modified_preserved"})
                continue
            if path.exists():
                path.unlink()
            store.db.execute("UPDATE exports SET state='removed' WHERE export_id=?", (row["export_id"],))
        except (OSError, CompanionError):
            exports.append({"export_id": row["export_id"], "state": "removal_blocked"})
    return {"removed": removed, "blocked": blocked, "exports": exports}


def maintain(store, limit=100):
    marker_path = store.state / "privacy-epoch.json"
    if marker_path.exists():
        marker = json.loads(read_bounded(marker_path, 65536))
        if marker.get("pending"):
            committed = store.db.execute("SELECT state FROM deletion_records WHERE deletion_id=?", (marker.get("deletion_id"),)).fetchone()
            if not committed:
                raise CompanionError("Interrupted privacy withdrawal has no committed tombstone; repeat the original withdrawal or review recovery")
            marker["pending"] = False
            atomic_write(marker_path, canonical(marker).encode())
    clock = datetime.now(timezone.utc)
    cutoff = (clock - timedelta(days=store.config.artifact_retention_days)).isoformat().replace("+00:00", "Z")
    with store.transaction():
        store.db.execute("UPDATE artifacts SET state='expired' WHERE state='available' AND artifact_id IN (SELECT artifact_id FROM artifacts WHERE created_at<? LIMIT ?)", (cutoff, limit))
        store.db.execute("UPDATE lessons SET status='expired' WHERE status='verified' AND expires_at IS NOT NULL AND expires_at<=?", (now(),))
    for row in store.db.execute("SELECT suppression_id FROM suppressions WHERE expires_at IS NOT NULL AND expires_at<=? LIMIT ?", (now(), limit)).fetchall():
        unsuppress(store, row[0])
    cleanup = purge_files(store, limit)
    response_cutoff = (clock - timedelta(days=store.config.event_retention_days)).timestamp()
    for path in sorted((store.state / "responses").glob("*.json"))[:limit]:
        if not path.is_symlink() and path.stat().st_mtime < response_cutoff:
            path.unlink()
    store.check_integrity()
    return {"status": "complete" if not cleanup["blocked"] else "incomplete", "artifact_cleanup": cleanup, "storage": store.status()["state_path"]}
