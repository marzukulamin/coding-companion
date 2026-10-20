"""Explicit loopback authorization matrices and concurrent HTTP acceptance steps."""
from __future__ import annotations

import argparse
import json
import tempfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from .api_probe import run as request_probe
except ImportError:  # Direct executable invocation through an approved native spec.
    from api_probe import run as request_probe


def batches(contract):
    if not isinstance(contract, dict):
        raise ValueError("Scenario contract must be an object")
    result = []
    matrix = contract.get("access_matrix")
    if matrix is not None:
        if not isinstance(matrix, dict):
            raise ValueError("Access matrix must be an object")
        actors, resources = matrix.get("actors"), matrix.get("resources")
        if not isinstance(actors, dict) or not 1 <= len(actors) <= 16 or not isinstance(resources, list) or not 1 <= len(resources) <= 20:
            raise ValueError("Access matrix requires bounded actors and resources")
        for actor, headers in actors.items():
            if not isinstance(actor, str) or not actor or len(actor) > 100 or not isinstance(headers, dict):
                raise ValueError("Each actor requires a name and synthetic request headers")
        for resource in resources:
            if not isinstance(resource, dict) or not isinstance(resource.get("expected_by_actor"), dict) or set(resource["expected_by_actor"]) != set(actors):
                raise ValueError("Every resource needs an explicit expectation for every actor")
            for actor, headers in actors.items():
                request = {key: value for key, value in resource.items() if key != "expected_by_actor"}
                request.update(id=f"matrix-{len(result)}-{actor}", headers=headers, expected=resource["expected_by_actor"][actor])
                result.append([request])
    steps = contract.get("steps", [])
    if not isinstance(steps, list) or len(steps) > 100:
        raise ValueError("Scenario step budget exceeded")
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("Scenario step must be an object")
        if "parallel" in step:
            group = step["parallel"]
            if set(step) != {"parallel"} or not isinstance(group, list) or not 2 <= len(group) <= 16 or any(not isinstance(item, dict) for item in group):
                raise ValueError("Parallel step needs 2–16 explicit requests")
            result.append(group)
        else:
            result.append([step])
    if not result or sum(map(len, result)) > 100:
        raise ValueError("Scenario requires 1–100 explicit requests")
    # Validate all expectations before running any active request.
    for batch in result:
        for request in batch:
            expected = request.get("expected")
            if not isinstance(expected, dict) or type(expected.get("status")) is not int or not 100 <= expected["status"] <= 599:
                raise ValueError("Each scenario request requires an explicit expected status")
    return result


def run(contract, report, allow_mutation=False):
    groups = batches(contract)
    if not allow_mutation and any(request.get("method", "GET") not in {"GET", "HEAD"} for group in groups for request in group):
        raise ValueError("Active scenarios require --allow-mutation before any request executes")
    report.parent.mkdir(parents=True, exist_ok=True)
    cases = []
    with tempfile.TemporaryDirectory(prefix="scenario-", dir=report.parent) as temporary:
        directory = Path(temporary)
        offset = 0
        for group in groups:
            def execute(item):
                index, request = item
                destination = directory / f"{index}.xml"
                request = {**request, "id": f"scenario-{index}"}
                request_probe({"base_url": contract.get("base_url"), "requests": [request]}, destination, allow_mutation)
                return ET.parse(destination).getroot().find("testcase")
            with ThreadPoolExecutor(max_workers=len(group)) as executor:
                # Batches finish before subsequent invariant/readback requests start.
                cases.extend(executor.map(execute, enumerate(group, offset)))
            offset += len(group)
    failed = sum(case.find("failure") is not None for case in cases)
    errors = sum(case.find("error") is not None for case in cases)
    suite = ET.Element("testsuite", tests=str(len(cases)), failures=str(failed), errors=str(errors))
    suite.extend(cases)
    ET.ElementTree(suite).write(report, encoding="utf-8", xml_declaration=True)
    return 1 if failed or errors else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--allow-mutation", action="store_true")
    args = parser.parse_args()
    with args.contract.open("rb") as handle:
        raw = handle.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("Scenario contract exceeds its byte limit")
    raise SystemExit(run(json.loads(raw), args.report, args.allow_mutation))
