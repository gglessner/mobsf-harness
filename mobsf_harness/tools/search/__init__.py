from __future__ import annotations

import json
from typing import Any, Protocol

from mobsf_harness.config import WebSearchConfig
from mobsf_harness.llm.types import ToolSchema
from mobsf_harness.tools.types import Tool, ToolContext

from .brave import BraveSearch
from .duckduckgo import DuckDuckGoSearch
from .tavily import TavilySearch


class WebSearch(Protocol):
    def search(self, query: str, limit: int = 5) -> list[dict]: ...


def make_web_search(cfg: WebSearchConfig) -> WebSearch:
    if cfg.backend == "tavily":
        return TavilySearch(api_key=cfg.api_key)
    if cfg.backend == "brave":
        return BraveSearch(api_key=cfg.api_key)
    if cfg.backend == "duckduckgo":
        return DuckDuckGoSearch()
    raise ValueError(f"unknown web_search backend: {cfg.backend}")


class WebSearchTool:
    """Adapter that exposes a WebSearch impl as an agent Tool."""
    def __init__(self, impl: WebSearch) -> None:
        self._impl = impl
        self._schema = ToolSchema(
            name="web_search",
            description=(
                "Search the web for CVE details, library advisories, or vendor docs. "
                "Use sparingly - prefer the report for facts about the app itself."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        )

    @property
    def schema(self) -> ToolSchema: return self._schema
    terminal = False

    def handler(self, args: dict[str, Any], ctx: ToolContext) -> str:
        try:
            hits = self._impl.search(args["query"], int(args.get("limit", 5)))
            return json.dumps({"results": hits})
        except Exception as e:
            return json.dumps({"error": str(e)})


def web_search_tool(cfg: WebSearchConfig) -> Tool:
    impl = make_web_search(cfg)
    inst = WebSearchTool(impl)
    return Tool(schema=inst.schema, handler=inst.handler, terminal=False)
