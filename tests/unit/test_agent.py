import json
from pathlib import Path

import pytest

from mobsf_harness.agent import AgentOutcome, FakeLlmClient, run_agent
from mobsf_harness.config import WebSearchConfig
from mobsf_harness.llm.types import LlmResponse, ToolCall
from mobsf_harness.state import StateStore
from mobsf_harness.tools import build_tool_registry


def _load_transcript(fixtures_dir: Path, name: str) -> list[LlmResponse]:
    data = json.loads((fixtures_dir / "llm_transcripts" / name).read_text())
    return [
        LlmResponse(
            text=r["text"],
            tool_calls=[
                ToolCall(id=c["id"], name=c["name"], arguments=c["arguments"])
                for c in r["tool_calls"]
            ],
            stop_reason=r["stop_reason"],
            usage_input_tokens=0,
            usage_output_tokens=0,
        )
        for r in data
    ]


@pytest.fixture
def state(tmp_path: Path) -> StateStore:
    s = StateStore(tmp_path / "s.sqlite")
    s.initialize()
    return s


@pytest.fixture
def report(fixtures_dir: Path) -> dict:
    return json.loads((fixtures_dir / "mobsf" / "small_report.json").read_text())


def test_happy_path_completes_with_summary(
    fixtures_dir: Path, tmp_path: Path, state: StateStore, report: dict
):
    responses = _load_transcript(fixtures_dir, "happy_path.json")
    client = FakeLlmClient(responses)
    app = state.get_or_create_app("android", "com.e", "play_store")
    scan = state.create_scan(app.id, "1", "1", "h", "r")

    outcome = run_agent(
        llm_client=client,
        model="fake",
        max_turns=10,
        max_tokens_per_session=10_000,
        tools=[t for t in build_tool_registry()],
        report_json=report,
        report_dir=tmp_path,
        summary_path=tmp_path / "summary.md",
        state=state,
        scan_id=scan.id,
        app_id=app.id,
        system="you are an analyst",
        user_prompt="analyze",
    )

    assert outcome.success is True
    assert outcome.turns == 3
    assert (tmp_path / "summary.md").read_text().startswith("# Summary")


def test_missing_summary_fails_safely(
    fixtures_dir: Path, tmp_path: Path, state: StateStore, report: dict
):
    responses = _load_transcript(fixtures_dir, "missing_summary.json")
    client = FakeLlmClient(responses)
    app = state.get_or_create_app("android", "com.e", "play_store")
    scan = state.create_scan(app.id, "1", "1", "h", "r")

    outcome = run_agent(
        llm_client=client,
        model="fake",
        max_turns=10,
        max_tokens_per_session=10_000,
        tools=[t for t in build_tool_registry()],
        report_json=report,
        report_dir=tmp_path,
        summary_path=tmp_path / "summary.md",
        state=state,
        scan_id=scan.id,
        app_id=app.id,
        system="s",
        user_prompt="u",
    )

    assert outcome.success is False
    assert "summary" in outcome.error
    notifs = state.notifications_for_scan(scan.id)
    assert any(n.channel == "log" for n in notifs)


def test_max_turns_enforced(
    tmp_path: Path, state: StateStore, report: dict
):
    loop_response = LlmResponse(
        text="",
        tool_calls=[ToolCall(id="x", name="get_report_section", arguments={"name": "severity"})],
        stop_reason="tool_use",
        usage_input_tokens=0,
        usage_output_tokens=0,
    )
    client = FakeLlmClient([loop_response] * 100)
    app = state.get_or_create_app("android", "com.e", "play_store")
    scan = state.create_scan(app.id, "1", "1", "h", "r")

    outcome = run_agent(
        llm_client=client,
        model="fake",
        max_turns=3,
        max_tokens_per_session=10_000,
        tools=[t for t in build_tool_registry()],
        report_json=report,
        report_dir=tmp_path,
        summary_path=tmp_path / "summary.md",
        state=state,
        scan_id=scan.id,
        app_id=app.id,
        system="s",
        user_prompt="u",
    )

    assert outcome.success is False
    assert outcome.turns == 3


def test_multiple_tool_calls_in_one_turn_emit_separate_tool_messages(
    tmp_path: Path, state: StateStore, report: dict
):
    """Regression: when the model makes multiple tool calls in one turn,
    the loop must emit one tool-role Message per ToolResult (OpenAI
    requires it; Anthropic handles it either way)."""
    responses = [
        LlmResponse(
            text="",
            tool_calls=[
                ToolCall(id="a", name="get_report_section", arguments={"name": "severity"}),
                ToolCall(id="b", name="get_report_section", arguments={"name": "permissions"}),
            ],
            stop_reason="tool_use",
            usage_input_tokens=0,
            usage_output_tokens=0,
        ),
        LlmResponse(
            text="",
            tool_calls=[
                ToolCall(id="c", name="write_summary", arguments={"markdown": "# ok"})
            ],
            stop_reason="tool_use",
            usage_input_tokens=0,
            usage_output_tokens=0,
        ),
        LlmResponse(
            text="done", tool_calls=[], stop_reason="end_turn",
            usage_input_tokens=0, usage_output_tokens=0,
        ),
    ]
    captured: list = []
    class _SpyClient(FakeLlmClient):
        def chat(self, *, system, messages, tools, model, max_output_tokens=4096):
            captured.append([m for m in messages])
            return super().chat(
                system=system, messages=messages, tools=tools,
                model=model, max_output_tokens=max_output_tokens,
            )
    client = _SpyClient(responses)
    app = state.get_or_create_app("android", "com.e", "play_store")
    scan = state.create_scan(app.id, "1", "1", "h", "r")

    outcome = run_agent(
        llm_client=client,
        model="fake",
        max_turns=10,
        max_tokens_per_session=10_000,
        tools=[t for t in build_tool_registry()],
        report_json=report,
        report_dir=tmp_path,
        summary_path=tmp_path / "summary.md",
        state=state,
        scan_id=scan.id,
        app_id=app.id,
        system="s",
        user_prompt="u",
    )

    assert outcome.success is True
    # On turn 2, the message history fed back to the LLM should contain
    # TWO separate tool-role messages (one per call from turn 1's response),
    # not a single tool-role message with two results.
    turn2_messages = captured[1]
    tool_msgs = [m for m in turn2_messages if m.role == "tool"]
    assert len(tool_msgs) == 2, f"expected 2 tool messages, got {len(tool_msgs)}"
    for m in tool_msgs:
        assert len(m.tool_results) == 1, "each tool message must carry exactly one result"
