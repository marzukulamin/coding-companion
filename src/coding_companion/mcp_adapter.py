"""Optional official SDK adapter. No homegrown protocol or HTTP transport."""
from __future__ import annotations

from .common import CompanionError


def serve(root, state, config):
    try:
        from mcp.server import MCPServer
        from mcp.types import ToolAnnotations
    except ImportError as exc:
        raise CompanionError("Optional MCP SDK 2.0.0 is not installed; use CLI checkpoints or install the mcp extra in a separate setup step") from exc
    from .cli import doctor, invoke

    server = MCPServer("coding-companion")
    readonly = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
    executable = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=True)

    @server.tool(annotations=readonly)
    def capabilities() -> dict:
        """Describe local runtime and host delivery boundaries."""
        return doctor()

    @server.tool(annotations=readonly)
    def discover_project() -> dict:
        """Inspect manifests, static local imports and declared coverage."""
        return invoke(root, state, config, "discover", {})

    @server.tool(annotations=readonly)
    def plan_checks(check_ids: list[str] | None = None, scope: str = "project") -> dict:
        """Plan known checks without executing project commands."""
        if scope not in {"project", "changed", "selected"}:
            raise CompanionError("Unknown scope")
        return invoke(root, state, config, "plan", {"checks": check_ids, "scope": scope})

    @server.tool(annotations=readonly)
    def get_run(run_id: str) -> dict:
        """Read a recorded result without rerunning its command."""
        return invoke(root, state, config, "get_run", {"run_id": run_id})

    @server.tool(annotations=executable)
    def record_feedback(finding_id: str, outcome: str, reason: str = "") -> dict:
        """Record explicit lifecycle feedback; resolution reruns verification."""
        if outcome not in {"resolved", "acknowledged", "investigating", "fixing", "dismissed", "accepted-risk"}:
            raise CompanionError("Unknown feedback outcome")
        return invoke(root, state, config, "feedback", {"finding_id": finding_id, "outcome": outcome, **({"reason": reason} if reason else {})})

    @server.tool(annotations=readonly)
    def list_challenges(actor: str = "all") -> dict:
        """Read bounded diagnostic challenges for this project."""
        if actor not in {"all", "coding_agent", "companion", "user", "external_tool"}:
            raise CompanionError("Unknown actor")
        return invoke(root, state, config, "challenges", {"actor": actor})

    @server.tool(annotations=executable)
    def start_checks(check_ids: list[str] | None = None) -> dict:
        """Run static checks or exact previously approved native check IDs."""
        return invoke(root, state, config, "check", {"checks": check_ids})

    @server.tool(annotations=readonly)
    def list_findings(since: int = 0) -> dict:
        """Read at most 100 observations after a delivery cursor."""
        if since < 0:
            raise CompanionError("Invalid cursor")
        return invoke(root, state, config, "findings", {"since": since})

    @server.tool(annotations=readonly)
    def inspect_finding(finding_id: str) -> dict:
        """Read finding evidence and tested snapshot identity."""
        return invoke(root, state, config, "inspect", {"finding_id": finding_id})

    @server.tool(annotations=executable)
    def verify_finding(finding_id: str) -> dict:
        """Rerun relevant current checks before resolving a finding."""
        return invoke(root, state, config, "verify", {"finding_id": finding_id})

    @server.tool(annotations=readonly)
    def search_memory(query: str) -> dict:
        """Retrieve bounded verified project lessons as diagnostic context."""
        return invoke(root, state, config, "memory_search", {"query": query})

    @server.tool(annotations=readonly)
    def export_report() -> dict:
        """Produce a bounded local Markdown diagnostic report."""
        return invoke(root, state, config, "report", {})

    server.run(transport="stdio")
    return {"status": "stopped"}
