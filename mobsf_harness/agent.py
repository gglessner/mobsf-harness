from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mobsf_harness.llm.types import LlmClient, LlmResponse, Message, ToolCall, ToolResult, ToolSchema
from mobsf_harness.state import StateStore
from mobsf_harness.tools.types import Tool, ToolContext


@dataclass
class AgentOutcome:
    success: bool
    turns: int
    error: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class FakeLlmClient:
    """Test double that replays a pre-scripted list of LlmResponse objects."""
    def __init__(self, responses: list[LlmResponse]) -> None:
        self._responses = list(responses)

    def chat(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSchema],
        model: str,
        max_output_tokens: int = 4096,
    ) -> LlmResponse:
        if not self._responses:
            raise RuntimeError("FakeLlmClient out of scripted responses")
        return self._responses.pop(0)


def _failsafe_notify(state: StateStore, scan_id: int, body: str) -> None:
    state.record_notification(scan_id, "log", "critical", body)


def run_agent(
    *,
    llm_client: LlmClient,
    model: str,
    max_turns: int,
    max_tokens_per_session: int,
    tools: list[Tool],
    report_json: dict[str, Any],
    report_dir: Path,
    summary_path: Path,
    state: StateStore,
    scan_id: int,
    app_id: int,
    system: str,
    user_prompt: str,
) -> AgentOutcome:
    notify_queue: list[dict] = []
    ctx = ToolContext(
        scan_id=scan_id,
        app_id=app_id,
        report_json=report_json,
        report_dir=report_dir,
        state=state,
        notify_queue=notify_queue,
        summary_path=summary_path,
    )
    by_name: dict[str, Tool] = {t.schema.name: t for t in tools}
    schemas = [t.schema for t in tools]
    messages: list[Message] = [Message(role="user", content=user_prompt)]

    total_in = total_out = 0
    summary_written = False

    for turn in range(1, max_turns + 1):
        rsp = llm_client.chat(
            system=system,
            messages=messages,
            tools=schemas,
            model=model,
        )
        total_in += rsp.usage_input_tokens
        total_out += rsp.usage_output_tokens

        if total_in + total_out > max_tokens_per_session:
            err = f"token budget exceeded ({total_in + total_out} > {max_tokens_per_session})"
            _failsafe_notify(state, scan_id, f"agent terminated: {err}")
            return AgentOutcome(
                success=False, turns=turn, error=err,
                total_input_tokens=total_in, total_output_tokens=total_out,
            )

        messages.append(
            Message(role="assistant", content=rsp.text, tool_calls=list(rsp.tool_calls))
        )

        if not rsp.tool_calls:
            if summary_written:
                return AgentOutcome(
                    success=True, turns=turn,
                    total_input_tokens=total_in, total_output_tokens=total_out,
                )
            err = "agent ended without calling write_summary"
            _failsafe_notify(state, scan_id, err)
            return AgentOutcome(
                success=False, turns=turn, error=err,
                total_input_tokens=total_in, total_output_tokens=total_out,
            )

        results: list[ToolResult] = []
        for call in rsp.tool_calls:
            tool = by_name.get(call.name)
            if tool is None:
                results.append(ToolResult(call_id=call.id, content=json.dumps({"error": f"unknown tool {call.name}"})))
                continue
            try:
                content = tool.handler(call.arguments, ctx)
            except Exception as e:
                content = json.dumps({"error": f"tool raised: {e}"})
            results.append(ToolResult(call_id=call.id, content=content))
            if call.name == "write_summary":
                try:
                    if json.loads(content).get("ok"):
                        summary_written = True
                except Exception:
                    pass
        # Emit one tool message per ToolResult — OpenAI's API requires this,
        # and Anthropic handles consecutive user messages fine.
        for r in results:
            messages.append(Message(role="tool", tool_results=[r]))

    err = f"max_turns reached ({max_turns})"
    _failsafe_notify(state, scan_id, err)
    return AgentOutcome(
        success=False, turns=max_turns, error=err,
        total_input_tokens=total_in, total_output_tokens=total_out,
    )
