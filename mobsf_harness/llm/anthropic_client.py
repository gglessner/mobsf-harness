from __future__ import annotations

from typing import Any

from anthropic import Anthropic

from .types import LlmResponse, Message, ToolCall, ToolResult, ToolSchema


class AnthropicClient:
    def __init__(self, api_key: str) -> None:
        self._sdk = Anthropic(api_key=api_key)

    def chat(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSchema],
        model: str,
        max_output_tokens: int = 4096,
    ) -> LlmResponse:
        sdk_messages = [self._to_sdk_message(m) for m in messages if m.role != "system"]
        sdk_tools = [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in tools
        ]
        rsp = self._sdk.messages.create(
            model=model,
            max_tokens=max_output_tokens,
            system=system,
            tools=sdk_tools,
            messages=sdk_messages,
        )
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in rsp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input)))
        return LlmResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=rsp.stop_reason,
            usage_input_tokens=rsp.usage.input_tokens,
            usage_output_tokens=rsp.usage.output_tokens,
        )

    @staticmethod
    def _to_sdk_message(m: Message) -> dict[str, Any]:
        if m.role == "tool":
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": r.call_id,
                        "content": r.content,
                    }
                    for r in m.tool_results
                ],
            }
        if m.role == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            for tc in m.tool_calls:
                blocks.append(
                    {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments}
                )
            return {"role": "assistant", "content": blocks}
        return {"role": "user", "content": m.content}
