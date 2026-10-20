from __future__ import annotations

import statistics
import math

from .common import CompanionError, digest


def paired(data):
    if not isinstance(data, dict) or not isinstance(data.get("trials"), list) or not 3 <= len(data["trials"]) <= 1000:
        raise CompanionError("Paired evaluation needs 3–1000 independently measured matched trials")
    differences, latency, tokens, false_alerts = [], [], [], []
    identities = set()
    for trial in data["trials"]:
        if not isinstance(trial, dict) or not all(key in trial for key in ("task_id", "fixture_hash", "agent_settings_hash", "environment_hash", "without", "with")):
            raise CompanionError("Trial must pin task, fixture, agent/settings and environment")
        identity = (trial["task_id"], trial.get("seed", 0))
        if identity in identities:
            raise CompanionError("Duplicate paired trial identity")
        identities.add(identity)
        for mode in ("without", "with"):
            result = trial[mode]
            if not isinstance(result, dict) or type(result.get("accepted")) is not bool or any(type(result.get(key)) not in (int, float) or not math.isfinite(result[key]) or result[key] < 0 for key in ("duration_seconds", "tokens", "cost_usd", "false_alerts", "user_interventions")):
                raise CompanionError("Trial outcomes must contain actual acceptance and nonnegative measured resource/alert/intervention values")
            if result.get("fixture_hash") != trial["fixture_hash"] or result.get("agent_settings_hash") != trial["agent_settings_hash"] or result.get("environment_hash") != trial["environment_hash"]:
                raise CompanionError("Paired trial configuration/evidence is mismatched")
        with_companion, baseline = trial["with"], trial["without"]
        if with_companion.get("includes_companion_overhead") is not True:
            raise CompanionError("Companion mode must include its own measured overhead")
        differences.append(int(with_companion["accepted"]) - int(baseline["accepted"]))
        latency.append(with_companion["duration_seconds"] - baseline["duration_seconds"])
        tokens.append(with_companion["tokens"] - baseline["tokens"])
        false_alerts.append(with_companion["false_alerts"])
    return {"status": "complete", "trials": len(differences), "accepted_task_delta": sum(differences), "mean_duration_delta_seconds": statistics.mean(latency), "mean_token_delta": statistics.mean(tokens), "false_alerts_with_companion": sum(false_alerts), "input_sha256": digest(data), "interpretation": "Measured supplied trials only; no universal superiority or independently verified agent-execution claim"}
