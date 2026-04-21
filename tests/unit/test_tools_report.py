import json
from pathlib import Path

import pytest

from mobsf_harness.state import StateStore
from mobsf_harness.tools.report import (
    GetPriorFindingHistory,
    GetReportSection,
)
from mobsf_harness.tools.types import ToolContext


@pytest.fixture
def state(tmp_path: Path) -> StateStore:
    s = StateStore(tmp_path / "s.sqlite")
    s.initialize()
    return s


@pytest.fixture
def report(fixtures_dir: Path) -> dict:
    return json.loads((fixtures_dir / "mobsf" / "small_report.json").read_text())


def _ctx(report, state, scan_id=1, app_id=1, tmp_path: Path | None = None) -> ToolContext:
    return ToolContext(
        scan_id=scan_id,
        app_id=app_id,
        report_json=report,
        report_dir=tmp_path or Path("."),
        state=state,
        notify_queue=[],
        summary_path=(tmp_path or Path(".")) / "summary.md",
    )


def test_get_report_section_returns_named_slice(report, state):
    tool = GetReportSection()
    result = tool.handler({"name": "permissions"}, _ctx(report, state))
    data = json.loads(result)
    assert "android.permission.INTERNET" in data


def test_get_report_section_rejects_unknown_name(report, state):
    tool = GetReportSection()
    result = tool.handler({"name": "not_a_section"}, _ctx(report, state))
    data = json.loads(result)
    assert "error" in data


def test_prior_finding_history_returns_past_occurrences(state, tmp_path):
    app = state.get_or_create_app("android", "com.e", "play_store")
    s1 = state.create_scan(app.id, "1.0", "1", "h1", "r1")
    state.update_scan_status(s1.id, "done")
    state.add_finding(s1.id, "RULE_A", "high", "t", {})
    s2 = state.create_scan(app.id, "1.1", "2", "h2", "r2")

    tool = GetPriorFindingHistory()
    result = tool.handler(
        {"finding_key": "RULE_A", "limit": 5},
        _ctx({}, state, scan_id=s2.id, app_id=app.id, tmp_path=tmp_path),
    )
    data = json.loads(result)
    assert data["count"] == 1
    assert data["history"][0]["severity"] == "high"
