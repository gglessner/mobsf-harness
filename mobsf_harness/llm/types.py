from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass
class ToolSchema:
    """Provider-agnostic tool description."""
    name: str
    description: str
    parameters: dict[str, Any]          # JSON Schema for the arguments


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    call_id: str
    content: str                        # serialized JSON or plain text


@dataclass
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""                   # text content
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)


@dataclass
class LlmResponse:
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str                    # "end_turn" | "tool_use" | "max_tokens" | ...
    usage_input_tokens: int
    usage_output_tokens: int


class LlmClient(Protocol):
    def chat(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSchema],
        model: str,
        max_output_tokens: int = 4096,
    ) -> LlmResponse: ...
