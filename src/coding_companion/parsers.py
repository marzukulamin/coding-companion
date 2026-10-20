from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from .common import CompanionError


def junit(data: bytes) -> dict:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise CompanionError("JUnit evidence must use UTF-8") from exc
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise CompanionError("Unsafe XML declarations rejected")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise CompanionError("Malformed JUnit evidence") from exc
    if root.tag not in {"testsuite", "testsuites"}:
        raise CompanionError("Unexpected JUnit root")
    cases = list(root.iter("testcase"))
    if not cases:
        raise CompanionError("JUnit report contains zero tests")
    skipped = sum(case.find("skipped") is not None for case in cases)
    failed = sum(case.find("failure") is not None or case.find("error") is not None for case in cases)
    # Native counts must agree with actual test cases, not unsupported summary claims.
    suites = [s for s in root.iter("testsuite") if not list(s.findall("testsuite"))]
    for suite in suites:
        if "tests" in suite.attrib:
            try:
                declared = int(suite.attrib["tests"])
            except ValueError as exc:
                raise CompanionError("Invalid JUnit test count") from exc
            if declared != len(list(suite.iter("testcase"))):
                raise CompanionError("JUnit count contradicts test cases")
        children = list(suite.iter("testcase"))
        measured = {"skipped": sum(c.find("skipped") is not None for c in children), "failures": sum(c.find("failure") is not None for c in children), "errors": sum(c.find("error") is not None for c in children)}
        for key, count in measured.items():
            if key in suite.attrib:
                try:
                    declared = int(suite.attrib[key])
                except ValueError as exc:
                    raise CompanionError("Invalid JUnit summary count") from exc
                if declared != count:
                    raise CompanionError("JUnit summary contradicts observed cases")
    if not len(cases) - skipped:
        raise CompanionError("JUnit report executed zero tests")
    from .common import digest
    identities = [digest({"classname": case.get("classname", ""), "name": case.get("name", f"anonymous-{index}")}) for index, case in enumerate(cases)]
    return {"counts": {"discovered": len(cases), "executed": len(cases) - skipped, "skipped": skipped}, "failed": failed, "case_ids": identities, "executed_case_ids": [identity for identity, case in zip(identities, cases) if case.find("skipped") is None], "failed_case_ids": [identity for identity, case in zip(identities, cases) if case.find("failure") is not None or case.find("error") is not None]}


def sarif(data: bytes) -> list[dict]:
    try:
        report = json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise CompanionError("Malformed SARIF evidence") from exc
    if not isinstance(report, dict) or report.get("version") != "2.1.0" or not isinstance(report.get("runs"), list):
        raise CompanionError("Expected SARIF 2.1.0 runs")
    items = []
    for run in report["runs"]:
        if not isinstance(run, dict) or not isinstance(run.get("results"), list):
            raise CompanionError("Missing SARIF results")
        for item in run["results"]:
            if not isinstance(item, dict) or not isinstance(item.get("message"), dict):
                raise CompanionError("Malformed SARIF finding")
            items.append(item)
            if len(items) > 1000:
                raise CompanionError("SARIF finding limit exceeded")
    return items
