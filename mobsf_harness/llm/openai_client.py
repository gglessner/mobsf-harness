from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from .types import LlmResponse, Message, ToolCall, ToolResult, ToolSchema


class OpenAICompatibleClient:
    def __init__(self, api_key: str, base_url: str) -> None:
        self._sdk = OpenAI(api_key=api_key, base_url=base_url)

    def chat(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSchema],
        model: str,
        max_output_tokens: int = 4096,
    ) -> LlmResponse:
        sdk_messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for m in messages:
            sdk_messages.append(self._to_sdk_message(m))
        sdk_tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]
        rsp = self._sdk.chat.completions.create(
            model=model,
            messages=sdk_messages,
            tools=sdk_tools,
            max_tokens=max_output_tokens,
        )
        choice = rsp.choices[0]
        tool_calls = []
        for tc in (choice.message.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": tc.function.arguments}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return LlmResponse(
            text=choice.message.content or "",
            tool_calls=tool_calls,
            stop_reason=choice.finish_reason,
            usage_input_tokens=rsp.usage.prompt_tokens,
            usage_output_tokens=rsp.usage.completion_tokens,
        )

    @staticmethod
    def _to_sdk_message(m: Message) -> dict[str, Any]:
        if m.role == "tool":
            if len(m.tool_results) == 1:
                r = m.tool_results[0]
                return {"role": "tool", "tool_call_id": r.call_id, "content": r.content}
            raise ValueError(
                "OpenAI-compatible: use one Message(role='tool') per ToolResult"
            )
        if m.role == "assistant":
            out: dict[str, Any] = {"role": "assistant", "content": m.content or None}
            if m.tool_calls:
                out["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in m.tool_calls
                ]
            return out
        return {"role": m.role, "content": m.content}
