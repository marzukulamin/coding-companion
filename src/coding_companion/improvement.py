from __future__ import annotations

import json
from importlib.resources import files

from . import __version__
from .common import CompanionError, canonical, digest, identifier, now, read_bounded, redact


def current_evidence(store, engine, finding_id: str, run_id: str):
    item = store.inspect(finding_id)
    run = store.db.execute("SELECT result_json,snapshot_id,check_id FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not run or item["lifecycle"] != "verified_resolved":
        raise CompanionError("Lesson evaluation requires a verified resolved finding")
    result = json.loads(run["result_json"])
    checks = item["observation"]["verification"]["checks"]
    if run["check_id"] not in checks or result.get("outcome") != "passed" or result.get("completeness") != "complete" or run["snapshot_id"] != engine.snapshot_for_checks(checks).snapshot_id:
        raise CompanionError("Lesson evidence is unsuitable, incomplete or stale")
    return item, result


def manage_improvement(store, engine, args):
    if args.action == "plan":
        return {"status": "planned", "implemented": ["verified_project_lessons", "lesson_evaluation", "reviewed_lesson_activation", "lesson_rollback", "rights_gated_local_ranking", "heldout_ranking_evaluation", "immutable_package_staging", "externally_attested_package_evaluation", "reviewed_package_activation_and_rollback", "paired_trial_analysis"], "unavailable": ["automatic_patch_generation", "candidate_execution_without_verified_isolation", "universal_product_superiority_certification"], "policy": "No automatic source rewrite or training; executable packages need explicit independent evaluation and activation review", "candidates": [dict(r) for r in store.db.execute("SELECT candidate_id,kind,state,evaluation_passed FROM improvement_candidates ORDER BY created_at DESC LIMIT 100")]}
    if args.action == "evaluate":
        if args.proposal is None:
            raise CompanionError("Lesson evaluation needs --proposal JSON_PATH")
        proposal = json.loads(read_bounded(args.proposal, 65536))
        required = {"kind", "summary", "finding_id", "verification_run_id"}
        if not isinstance(proposal, dict) or set(proposal) != required or proposal.get("kind") != "lesson":
            raise CompanionError("Only nonexecutable project lesson proposals are supported")
        if not isinstance(proposal["summary"], str) or not proposal["summary"] or len(proposal["summary"]) > 4000:
            raise CompanionError("Lesson summary must have 1–4000 characters")
        proposal["summary"] = redact(proposal["summary"])
        item, result = current_evidence(store, engine, proposal["finding_id"], proposal["verification_run_id"])
        evaluator = digest(files("coding_companion").joinpath("improvement.py").read_bytes())
        candidate = identifier()
        # For nonexecutable lessons the evaluator is external to the proposed content.
        # This gate is evidence validation, not a measured held-out product benchmark.
        store.insert("improvement_candidates", candidate_id=candidate, kind="lesson", base_version=__version__, base_package_sha256=digest({"version": __version__, "evaluator": evaluator}), proposed_hash=digest(proposal), evaluator_sha256=evaluator, heldout_fixture_sha256=digest(result), proposal_json=canonical(proposal), evaluation_json=canonical({"passed": True, "basis": "current_verified_repair", "benchmark": "not_performed"}), state="evaluated", evaluation_passed=1, approval_json="{}", created_at=now())
        return {"status": "evaluated", "candidate_id": candidate, "proposed_hash": digest(proposal), "gate": "Current repair evidence only; no generalization or superiority claim"}
    if not args.candidate:
        raise CompanionError("Activation/rollback needs --candidate ID")
    row = store.db.execute("SELECT * FROM improvement_candidates WHERE candidate_id=?", (args.candidate,)).fetchone()
    if not row:
        raise CompanionError("Unknown improvement candidate")
    proposal = json.loads(row["proposal_json"])
    if row["kind"] != "lesson" or digest(proposal) != row["proposed_hash"]:
        raise CompanionError("Unsupported or changed candidate")
    if args.action == "activate":
        if not args.approve:
            raise CompanionError("Review the evaluated proposal and supply --approve to activate this project lesson")
        if row["state"] != "evaluated" or not row["evaluation_passed"]:
            raise CompanionError("Only evaluated candidates may activate")
        if digest(files("coding_companion").joinpath("improvement.py").read_bytes()) != row["evaluator_sha256"]:
            raise CompanionError("Evaluator changed; reevaluate before activation")
        current_evidence(store, engine, proposal["finding_id"], proposal["verification_run_id"])
        with store.transaction():
            lesson_id = store.save_lesson(proposal["finding_id"], proposal["verification_run_id"], proposal["summary"])
            store.db.execute("UPDATE improvement_candidates SET state='active',activated_at=?,approval_json=? WHERE candidate_id=?", (now(), canonical({"actor": "user", "proposed_hash": row["proposed_hash"], "lesson_id": lesson_id}), args.candidate))
            store.audit("activate_lesson", "candidate", args.candidate)
        return {"status": "active", "lesson_id": lesson_id, "candidate_id": args.candidate}
    if row["state"] != "active":
        raise CompanionError("Only an active candidate can roll back")
    approval = json.loads(row["approval_json"])
    with store.transaction():
        store.db.execute("UPDATE lessons SET status='revoked' WHERE lesson_id=?", (approval["lesson_id"],))
        store.db.execute("UPDATE improvement_candidates SET state='rolled_back' WHERE candidate_id=?", (args.candidate,))
        store.audit("rollback_lesson", "candidate", args.candidate)
    return {"status": "rolled_back", "candidate_id": args.candidate}
