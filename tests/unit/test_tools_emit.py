from pathlib import Path

import pytest

from mobsf_harness.state import StateStore
from mobsf_harness.tools.emit import Notify, WriteSummary
from mobsf_harness.tools.types import ToolContext


@pytest.fixture
def ctx(tmp_path: Path) -> ToolContext:
    state = StateStore(tmp_path / "s.sqlite")
    state.initialize()
    app = state.get_or_create_app("android", "com.e", "play_store")
    scan = state.create_scan(app.id, "1", "1", "h", "r")
    return ToolContext(
        scan_id=scan.id,
        app_id=app.id,
        report_json={},
        report_dir=tmp_path,
        state=state,
        notify_queue=[],
        summary_path=tmp_path / "summary.md",
    )


def test_write_summary_writes_file_and_is_idempotent(ctx: ToolContext):
    tool = WriteSummary()
    tool.handler({"markdown": "# summary"}, ctx)
    assert ctx.summary_path.read_text() == "# summary"
    tool.handler({"markdown": "# revised"}, ctx)
    assert ctx.summary_path.read_text() == "# revised"


def test_write_summary_rejects_empty(ctx: ToolContext):
    tool = WriteSummary()
    result = tool.handler({"markdown": ""}, ctx)
    assert "error" in result


def test_notify_queues_intent_and_persists(ctx: ToolContext):
    tool = Notify()
    result = tool.handler(
        {"channel": "any", "severity": "high", "title": "new finding", "body": "details"},
        ctx,
    )
    assert "ok" in result
    assert len(ctx.notify_queue) == 1
    assert ctx.notify_queue[0]["channel"] == "any"
    persisted = ctx.state.notifications_for_scan(ctx.scan_id)
    assert len(persisted) == 1
    assert persisted[0].body.startswith("new finding")


def test_notify_rejects_bad_channel(ctx: ToolContext):
    tool = Notify()
    result = tool.handler(
        {"channel": "nope", "severity": "high", "title": "t", "body": "b"},
        ctx,
    )
    assert "error" in result
    assert ctx.notify_queue == []
