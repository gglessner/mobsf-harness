from __future__ import annotations

from .emit import Notify, WriteSummary
from .report import GetPriorFindingHistory, GetReportSection
from .types import Tool, ToolContext


def _wrap(instance) -> Tool:
    return Tool(
        schema=instance.schema,
        handler=instance.handler,
        terminal=getattr(instance, "terminal", False),
    )


def build_tool_registry() -> list[Tool]:
    return [
        _wrap(GetReportSection()),
        _wrap(GetPriorFindingHistory()),
        _wrap(WriteSummary()),
        _wrap(Notify()),
    ]


__all__ = ["build_tool_registry", "Tool", "ToolContext"]
