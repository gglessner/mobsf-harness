from __future__ import annotations

import json
from typing import Any

from mobsf_harness.llm.types import ToolSchema

from .types import ToolContext


_VALID_CHANNELS = {"log", "email", "webhook", "any"}
_VALID_SEVERITIES = {"info", "low", "medium", "high", "critical"}


class WriteSummary:
    terminal = True

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="write_summary",
            description=(
                "Record the executive summary for this scan as markdown. "
                "Must be called exactly once. After calling, the loop should end."
            ),
            parameters={
                "type": "object",
                "properties": {"markdown": {"type": "string"}},
                "required": ["markdown"],
            },
        )

    def handler(self, args: dict[str, Any], ctx: ToolContext) -> str:
        md = args.get("markdown", "").strip()
        if not md:
            return json.dumps({"error": "markdown must be non-empty"})
        ctx.summary_path.parent.mkdir(parents=True, exist_ok=True)
        ctx.summary_path.write_text(md)
        return json.dumps({"ok": True, "bytes": len(md)})


class Notify:
    terminal = True

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="notify",
            description=(
                "Emit a notification the operator should see. Use sparingly - "
                "prefer signal over noise. Channel 'any' means route to every "
                "channel enabled in config; specific channels ('log', 'email', "
                "'webhook') constrain routing."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "enum": ["log", "email", "webhook", "any"]},
                    "severity": {"type": "string", "enum": sorted(_VALID_SEVERITIES)},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["channel", "severity", "title", "body"],
            },
        )

    def handler(self, args: dict[str, Any], ctx: ToolContext) -> str:
        channel = args.get("channel", "")
        severity = args.get("severity", "")
        title = args.get("title", "").strip()
        body = args.get("body", "").strip()
        if channel not in _VALID_CHANNELS:
            return json.dumps({"error": f"invalid channel {channel!r}"})
        if severity not in _VALID_SEVERITIES:
            return json.dumps({"error": f"invalid severity {severity!r}"})
        if not title or not body:
            return json.dumps({"error": "title and body required"})
        composed = f"{title}\n\n{body}"
        ctx.notify_queue.append(
            {"channel": channel, "severity": severity, "title": title, "body": body}
        )
        ctx.state.record_notification(ctx.scan_id, channel, severity, composed)
        return json.dumps({"ok": True})
