import json
from unittest.mock import MagicMock, patch

from mobsf_harness.llm.openai_client import OpenAICompatibleClient
from mobsf_harness.llm.types import Message, ToolCall, ToolResult, ToolSchema


def _tool() -> ToolSchema:
    return ToolSchema(
        name="write_summary",
        description="write the summary",
        parameters={"type": "object", "properties": {"markdown": {"type": "string"}}},
    )


@patch("mobsf_harness.llm.openai_client.OpenAI")
def test_chat_extracts_content_and_tool_calls(MockSDK):
    sdk = MagicMock()
    MockSDK.return_value = sdk
    tc = MagicMock()
    tc.id = "call_1"
    tc.function.name = "write_summary"
    tc.function.arguments = json.dumps({"markdown": "hi"})
    msg = MagicMock()
    msg.content = "thinking"
    msg.tool_calls = [tc]
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "tool_calls"
    rsp = MagicMock()
    rsp.choices = [choice]
    rsp.usage.prompt_tokens = 10
    rsp.usage.completion_tokens = 20
    sdk.chat.completions.create.return_value = rsp

    client = OpenAICompatibleClient(api_key="x", base_url="http://local/v1")
    result = client.chat(
        system="S",
        messages=[Message(role="user", content="go")],
        tools=[_tool()],
        model="gpt-4o",
    )

    assert result.text == "thinking"
    assert result.tool_calls == [ToolCall(id="call_1", name="write_summary", arguments={"markdown": "hi"})]
    assert result.stop_reason == "tool_calls"

    kwargs = sdk.chat.completions.create.call_args.kwargs
    assert kwargs["tools"][0]["type"] == "function"
    assert kwargs["tools"][0]["function"]["name"] == "write_summary"
    assert kwargs["messages"][0]["role"] == "system"
    assert kwargs["messages"][0]["content"] == "S"


@patch("mobsf_harness.llm.openai_client.OpenAI")
def test_tool_result_roundtrip(MockSDK):
    sdk = MagicMock()
    MockSDK.return_value = sdk
    msg = MagicMock(); msg.content = "done"; msg.tool_calls = None
    choice = MagicMock(); choice.message = msg; choice.finish_reason = "stop"
    rsp = MagicMock(); rsp.choices=[choice]; rsp.usage.prompt_tokens=0; rsp.usage.completion_tokens=0
    sdk.chat.completions.create.return_value = rsp

    msgs = [
        Message(role="user", content="go"),
        Message(
            role="assistant",
            content="thinking",
            tool_calls=[ToolCall(id="c1", name="t", arguments={"a": 1})],
        ),
        Message(role="tool", tool_results=[ToolResult(call_id="c1", content='{"ok":true}')]),
    ]
    OpenAICompatibleClient("x", "http://local/v1").chat(system="S", messages=msgs, tools=[_tool()], model="m")

    sent = sdk.chat.completions.create.call_args.kwargs["messages"]
    assert sent[2]["role"] == "assistant"
    assert sent[2]["tool_calls"][0]["id"] == "c1"
    assert sent[3]["role"] == "tool"
    assert sent[3]["tool_call_id"] == "c1"
    assert sent[3]["content"] == '{"ok":true}'
