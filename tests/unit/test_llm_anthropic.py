from unittest.mock import MagicMock, patch

from mobsf_harness.llm.anthropic_client import AnthropicClient
from mobsf_harness.llm.types import Message, ToolCall, ToolResult, ToolSchema


def _tool() -> ToolSchema:
    return ToolSchema(
        name="write_summary",
        description="write the summary",
        parameters={"type": "object", "properties": {"markdown": {"type": "string"}}},
    )


@patch("mobsf_harness.llm.anthropic_client.Anthropic")
def test_chat_extracts_text_and_tool_calls(MockSDK):
    sdk = MagicMock()
    MockSDK.return_value = sdk
    rsp = MagicMock()
    rsp.stop_reason = "tool_use"
    rsp.usage.input_tokens = 100
    rsp.usage.output_tokens = 50
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "thinking..."
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "call_1"
    tool_block.name = "write_summary"
    tool_block.input = {"markdown": "hi"}
    rsp.content = [text_block, tool_block]
    sdk.messages.create.return_value = rsp

    client = AnthropicClient(api_key="x")
    result = client.chat(
        system="S",
        messages=[Message(role="user", content="hi")],
        tools=[_tool()],
        model="claude-opus-4-7",
    )

    assert result.text == "thinking..."
    assert result.tool_calls == [ToolCall(id="call_1", name="write_summary", arguments={"markdown": "hi"})]
    assert result.stop_reason == "tool_use"
    assert result.usage_input_tokens == 100

    kwargs = sdk.messages.create.call_args.kwargs
    assert kwargs["system"] == "S"
    assert kwargs["model"] == "claude-opus-4-7"
    assert kwargs["tools"][0]["name"] == "write_summary"
    assert kwargs["tools"][0]["input_schema"]["type"] == "object"


@patch("mobsf_harness.llm.anthropic_client.Anthropic")
def test_tool_results_roundtrip(MockSDK):
    sdk = MagicMock()
    MockSDK.return_value = sdk
    rsp = MagicMock()
    rsp.stop_reason = "end_turn"
    rsp.usage.input_tokens = 1
    rsp.usage.output_tokens = 1
    rsp.content = [MagicMock(type="text", text="done")]
    sdk.messages.create.return_value = rsp

    client = AnthropicClient(api_key="x")
    msgs = [
        Message(role="user", content="go"),
        Message(
            role="assistant",
            content="thinking",
            tool_calls=[ToolCall(id="c1", name="t", arguments={"a": 1})],
        ),
        Message(role="tool", tool_results=[ToolResult(call_id="c1", content='{"ok": true}')]),
    ]
    client.chat(system="S", messages=msgs, tools=[_tool()], model="m")

    sent = sdk.messages.create.call_args.kwargs["messages"]
    assert sent[1]["role"] == "assistant"
    assert any(b["type"] == "tool_use" and b["id"] == "c1" for b in sent[1]["content"])
    assert sent[2]["role"] == "user"
    assert sent[2]["content"][0]["type"] == "tool_result"
    assert sent[2]["content"][0]["tool_use_id"] == "c1"
