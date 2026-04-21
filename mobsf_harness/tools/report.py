from __future__ import annotations

import json
from typing import Any

from mobsf_harness.llm.types import ToolSchema

from .types import Tool, ToolContext


_KNOWN_SECTIONS = {
    "manifest": "manifest_analysis",
    "permissions": "permissions",
    "code_analysis": "code_analysis",
    "network": "network_security",
    "secrets": "secrets",
    "severity": "severity",
}


class GetReportSection:
    def __init__(self) -> None:
        self._schema = ToolSchema(
            name="get_report_section",
            description=(
                "Fetch a named slice of the current MOBSF report JSON. "
                f"Valid names: {sorted(_KNOWN_SECTIONS)}."
            ),
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        )

    @property
    def schema(self) -> ToolSchema: return self._schema
    terminal = False

    def handler(self, args: dict[str, Any], ctx: ToolContext) -> str:
        name = args.get("name", "")
        key = _KNOWN_SECTIONS.get(name)
        if not key:
            return json.dumps({"error": f"unknown section '{name}'", "valid": sorted(_KNOWN_SECTIONS)})
        return json.dumps(ctx.report_json.get(key, {}))


class GetPriorFindingHistory:
    def __init__(self) -> None:
        self._schema = ToolSchema(
            name="get_prior_finding_history",
            description=(
                "Return past occurrences of a finding in prior scans of this app. "
                "Use this to decide whether a finding is new or recurring."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "finding_key": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["finding_key"],
            },
        )

    @property
    def schema(self) -> ToolSchema: return self._schema
    terminal = False

    def handler(self, args: dict[str, Any], ctx: ToolContext) -> str:
        finding_key = args["finding_key"]
        limit = int(args.get("limit", 5))
        history = ctx.state.prior_finding_history(
            ctx.app_id, finding_key, before_scan_id=ctx.scan_id, limit=limit
        )
        return json.dumps(
            {
                "count": len(history),
                "history": [
                    {"severity": f.severity, "title": f.title, "scan_id": f.scan_id}
                    for f in history
                ],
            }
        )
