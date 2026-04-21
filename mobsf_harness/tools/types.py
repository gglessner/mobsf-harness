from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from mobsf_harness.llm.types import ToolSchema


@dataclass
class Tool:
    schema: ToolSchema
    handler: Callable[[dict[str, Any], "ToolContext"], str]
    terminal: bool = False


@dataclass
class ToolContext:
    """Passed to every tool handler so the tool can reach state / config / fs."""
    scan_id: int
    app_id: int
    report_json: dict[str, Any]
    report_dir: Any
    state: Any
    notify_queue: list
    summary_path: Any
