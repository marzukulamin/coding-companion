"""Full JSON Schema validation and real optional SDK stdio acceptance."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import site
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


async def validate_mcp(dependencies: Path):
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary).resolve()
        project = base / "project"
        project.mkdir()
        (project / "main.py").write_text("value = (", encoding="utf-8")
        arguments = ["mcp", "--project", str(project), "--state-dir", str(base / "state")]
        bootstrap = f"import sys,site;site.addsitedir({str(dependencies)!r});sys.path[:0]={[str(dependencies), str(ROOT / 'src')]!r};from coding_companion.cli import main;raise SystemExit(main({arguments!r}))"
        parameters = StdioServerParameters(command=sys.executable, args=["-I", "-c", bootstrap])
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                annotations = {tool.name: tool.annotations for tool in tools.tools}
                assert annotations["capabilities"].read_only_hint
                assert not annotations["start_checks"].read_only_hint
                assert {"capabilities", "discover_project", "plan_checks", "start_checks", "get_run", "list_findings", "inspect_finding", "verify_finding", "record_feedback", "list_challenges", "search_memory", "export_report"} <= names
                def body(result):
                    assert not result.is_error, result
                    if result.structured_content is not None:
                        return result.structured_content
                    return json.loads(result.content[0].text)
                health = body(await session.call_tool("capabilities"))
                assert health["status"] == "passed"
                checked = body(await session.call_tool("start_checks", {"check_ids": ["python.syntax"]}))
                assert checked["status"] == "failed", checked
                fid = checked["results"][0]["findings"][0]["finding_id"]
                inspected = body(await session.call_tool("inspect_finding", {"finding_id": fid}))
                assert inspected["classification"] == "confirmed_defect"
                (project / "main.py").write_text("value = 1", encoding="utf-8")
                verified = body(await session.call_tool("verify_finding", {"finding_id": fid}))
                assert verified["resolution"] == "verified_resolved", verified
                return {"status": "passed", "protocol": initialized.protocol_version, "sdk": "2.0.0", "tools": len(names), "real_checks": ["initialize", "list_tools", "native_structured_output", "seeded_defect", "inspect", "repair_verification"]}


def validate_schemas():
    from jsonschema import Draft202012Validator, FormatChecker
    schema = json.loads((ROOT / "design/contracts.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    examples = json.loads((ROOT / "design/examples.json").read_text(encoding="utf-8"))
    examples.append(json.loads((ROOT / "design/checks.example.json").read_text(encoding="utf-8")))
    for example in examples:
        validator.validate(example)
    control = json.loads((ROOT / "src/coding_companion/resources/control.schema.json").read_text())
    Draft202012Validator.check_schema(control)
    control_validator = Draft202012Validator(control, format_checker=FormatChecker())
    sys.path.insert(0, str(ROOT / "src"))
    from coding_companion.cli import invoke
    from coding_companion.config import Config, state_root
    from coding_companion.mailbox import validate
    from coding_companion.common import CompanionError, identifier, now
    pid = "a" * 32
    requests = []
    for operation, args in (("status", {}), ("check", {"checks": ["python.syntax"], "reuse": True}), ("verify", {"finding_id": "f"}), ("feedback", {"finding_id": "f", "outcome": "resolved"})):
        request = {"schema_version": "1.0", "request_id": identifier(), "project_id": pid, "operation": operation, "args": args, "created_at": now(), "deadline_at": now()}
        control_validator.validate(request)
        validate(request, pid)
        requests.append(request)
    for invalid in ({**requests[0], "operation": []}, {**requests[1], "args": {"scope": []}}, {**requests[0], "args": {"command": "unapproved"}}):
        assert not control_validator.is_valid(invalid)
        try:
            validate(invalid, pid)
        except CompanionError:
            pass
        else:
            raise AssertionError("Runtime/control schema conformance mismatch")
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary).resolve()
        project = base / "project"
        project.mkdir()
        (project / "main.py").write_text("broken = (", encoding="utf-8")
        report = invoke(project, state_root(project, base / "state"), Config(), "check", {})
        for result in report["results"]:
            validator.validate(result)
    return {"status": "passed", "draft": "2020-12", "design_examples": len(examples), "runtime_results": len(report["results"]), "control_conformance_cases": 7}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dependencies", type=Path, required=True)
    args = parser.parse_args()
    dependencies = args.dependencies.resolve()
    site.addsitedir(str(dependencies))
    sys.path.insert(0, str(dependencies))
    print(json.dumps({"schema": validate_schemas(), "mcp": asyncio.run(validate_mcp(dependencies))}, indent=2))
