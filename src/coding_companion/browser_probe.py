"""Optional, explicitly approved rendered-browser contract probe."""
from __future__ import annotations

import argparse
import json
import site
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin, urlsplit


def run(contract, report: Path, executable=None):
    from playwright.sync_api import sync_playwright
    base = contract.get("base_url", "")
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.username or parsed.password:
        raise ValueError("Browser probe v1 requires an explicitly supplied loopback test URL")
    origin = (parsed.scheme, parsed.netloc)
    routes, viewports, checks = contract.get("paths"), contract.get("viewports"), contract.get("checks")
    known = {"no_console_errors", "no_failed_resources", "no_root_overflow", "images_have_alternatives", "selector_visible", "selector_focusable", "selector_focused", "selector_receives_pointer"}
    if not isinstance(routes, list) or not 1 <= len(routes) <= 20 or any(not isinstance(p, str) or not p.startswith("/") or p.startswith("//") for p in routes):
        raise ValueError("Contract requires 1–20 relative test routes")
    if not isinstance(viewports, list) or not 1 <= len(viewports) <= 10 or any(type(v.get("width")) is not int or type(v.get("height")) is not int or not 200 <= v["width"] <= 4000 or not 200 <= v["height"] <= 4000 for v in viewports):
        raise ValueError("Contract requires bounded viewport dimensions")
    if not isinstance(checks, list) or not 1 <= len(checks) <= 20 or any(not isinstance(c, dict) or c.get("kind") not in known for c in checks):
        raise ValueError("Contract requires explicit supported browser assertions")
    if len(routes) * len(viewports) * len(checks) > 1000:
        raise ValueError("Browser assertion budget exceeded")
    cases, failed = [], 0
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(str(report.parent / "browser-profile"), headless=True, executable_path=executable, service_workers="block", accept_downloads=False)
        try:
            def route_request(route):
                target = urlsplit(route.request.url)
                if (target.scheme, target.netloc) == origin or target.scheme in {"data", "about"}:
                    route.continue_()
                else:
                    route.abort()
            context.route("**/*", route_request)
            for viewport in viewports:
                for route in routes:
                    page = context.new_page()
                    page.set_default_timeout(5000)
                    page.set_viewport_size(viewport)
                    console, resources = [], []
                    page.on("pageerror", lambda error: console.append(True) if len(console) < 1000 else None)
                    page.on("console", lambda message: console.append(True) if message.type == "error" and len(console) < 1000 else None)
                    page.on("requestfailed", lambda request: resources.append(True) if len(resources) < 1000 else None)
                    page.on("response", lambda response: resources.append(True) if response.status >= 400 and len(resources) < 1000 else None)
                    try:
                        response = page.goto(urljoin(base, route), wait_until="load", timeout=10000)
                        if response is None or response.status >= 400:
                            raise ValueError("Test route did not return a successful document")
                        actions = contract.get("actions", [])
                        if not isinstance(actions, list) or len(actions) > 50:
                            raise ValueError("Action budget exceeded")
                        for action in actions:
                            locator = page.locator(action["selector"])
                            if action["kind"] == "click":
                                locator.click()
                            elif action["kind"] == "fill" and isinstance(action.get("value"), str):
                                locator.fill(action["value"])
                            elif action["kind"] == "focus":
                                locator.focus()
                            elif action["kind"] == "press" and action.get("key") in {"Tab", "Shift+Tab", "Enter", "Space", "Escape", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End"}:
                                locator.press(action["key"])
                            else:
                                raise ValueError("Unsupported declared browser action")
                        for check in checks:
                            kind = check["kind"]
                            case = ET.Element("testcase", name=f"{route}:{viewport['width']}x{viewport['height']}:{kind}")
                            if kind == "no_console_errors":
                                passed, actual = not console, {"console_errors": len(console)}
                            elif kind == "no_failed_resources":
                                passed, actual = not resources, {"failed_resources": len(resources)}
                            elif kind == "no_root_overflow":
                                actual = page.evaluate("({scrollWidth:document.documentElement.scrollWidth,viewportWidth:innerWidth})")
                                passed = actual["scrollWidth"] <= actual["viewportWidth"] + 1
                            elif kind == "images_have_alternatives":
                                missing = page.locator("img:not([alt])").count()
                                passed, actual = missing == 0, {"missing_alternatives": missing}
                            else:
                                locator = page.locator(check["selector"])
                                passed = locator.count() == 1 and locator.is_visible()
                                if kind == "selector_focusable" and passed:
                                    locator.focus()
                                    passed = locator.evaluate("node => document.activeElement === node")
                                elif kind == "selector_focused" and passed:
                                    passed = locator.evaluate("node => document.activeElement === node")
                                elif kind == "selector_receives_pointer" and passed:
                                    locator.scroll_into_view_if_needed()
                                    passed = locator.evaluate("""node => {
                                        const r = node.getBoundingClientRect();
                                        const x = (Math.max(0,r.left)+Math.min(innerWidth,r.right))/2;
                                        const y = (Math.max(0,r.top)+Math.min(innerHeight,r.bottom))/2;
                                        if (r.width <= 0 || r.height <= 0 || x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return false;
                                        const hit = document.elementFromPoint(x,y);
                                        return hit === node || node.contains(hit);
                                    }""")
                                actual = {"matches_contract": passed}
                            ET.SubElement(case, "system-out").text = json.dumps({"viewport": viewport, "check": kind, "actual": actual})
                            if not passed:
                                ET.SubElement(case, "failure", message="Declared rendered-browser acceptance assertion failed")
                                failed += 1
                            cases.append(case)
                    except Exception as exc:
                        case = ET.Element("testcase", name=f"{route}:browser-environment")
                        ET.SubElement(case, "error", message=type(exc).__name__)
                        cases.append(case)
                        failed += 1
                    finally:
                        page.close()
        finally:
            context.close()
    suite = ET.Element("testsuite", tests=str(len(cases)), failures=str(sum(c.find("failure") is not None for c in cases)), errors=str(sum(c.find("error") is not None for c in cases)))
    suite.extend(cases)
    report.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite).write(report, encoding="utf-8", xml_declaration=True)
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--dependency-dir", type=Path, help="Explicit isolated SDK installation for development; ordinary installed extras need no override")
    args = parser.parse_args()
    if args.dependency_dir:
        site.addsitedir(str(args.dependency_dir.resolve()))
    with args.contract.open("rb") as handle:
        data = handle.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("Browser contract byte limit exceeded")
    return run(json.loads(data), args.report, str(args.executable) if args.executable else None)


if __name__ == "__main__":
    raise SystemExit(main())
