"""Stdlib loopback HTTP contract probe. No arbitrary shell or production URL."""
from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin, urlsplit


def run(contract, report, allow_mutation=False):
    base = contract.get("base_url", "")
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password:
        raise ValueError("HTTP probe requires an explicit loopback test URL")
    scenarios = contract.get("requests")
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 100:
        raise ValueError("HTTP contract requires 1–100 explicit request expectations")
    class SameOrigin(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            target = urlsplit(newurl)
            if (target.scheme, target.netloc) != (parsed.scheme, parsed.netloc):
                raise ValueError("Cross-origin redirect blocked")
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), SameOrigin())
    cases = []
    for index, scenario in enumerate(scenarios):
        case = ET.Element("testcase", name=str(scenario.get("id", f"request-{index}")))
        try:
            method, path = scenario.get("method", "GET"), scenario["path"]
            if method not in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"} or (method not in {"GET", "HEAD"} and not allow_mutation):
                raise ValueError("Mutating/active HTTP methods require --allow-mutation")
            if not isinstance(path, str) or not path.startswith("/") or path.startswith("//") or "\\" in path:
                raise ValueError("Request path must stay within the test origin")
            headers = scenario.get("headers", {})
            if not isinstance(headers, dict) or len(headers) > 30 or any(not re.fullmatch(r"[A-Za-z0-9_-]+", key) or not isinstance(value, str) or len(value) > 2000 or "\r" in value or "\n" in value for key, value in headers.items()):
                raise ValueError("Invalid bounded request headers")
            expected = scenario.get("expected")
            if not isinstance(expected, dict) or type(expected.get("status")) is not int or not 100 <= expected["status"] <= 599:
                raise ValueError("Explicit expected HTTP status is required")
            payload = json.dumps(scenario["json"], allow_nan=False).encode() if "json" in scenario else None
            if payload is not None and len(payload) > 1024 * 1024:
                raise ValueError("Request body budget exceeded")
            request = urllib.request.Request(urljoin(base, path), data=payload, headers=headers, method=method)
            try:
                response = opener.open(request, timeout=5)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                status, content_type = response.status, response.headers.get("Content-Type", "")
                body = response.read(1024 * 1024 + 1)
            if len(body) > 1024 * 1024:
                raise ValueError("Response body budget exceeded")
            passed = status == expected["status"]
            if "content_type" in expected:
                passed &= content_type.split(";", 1)[0] == expected["content_type"]
            if "json_fields" in expected:
                actual = json.loads(body)
                passed &= isinstance(actual, dict) and all(actual.get(key) == value for key, value in expected["json_fields"].items())
            if "headers" in expected:
                passed &= all(response.headers.get(key) == value for key, value in expected["headers"].items())
            ET.SubElement(case, "system-out").text = json.dumps({"actual_status": status, "response_bytes": len(body), "expectation_matched": bool(passed)})
            if not passed:
                ET.SubElement(case, "failure", message="Declared HTTP acceptance contract failed")
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
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--allow-mutation", action="store_true")
    args = parser.parse_args()
    with args.contract.open("rb") as handle:
        raw = handle.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("HTTP contract exceeds its byte limit")
    raise SystemExit(run(json.loads(raw), args.report, args.allow_mutation))
