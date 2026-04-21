import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mobsf_harness.agent import FakeLlmClient
from mobsf_harness.config import (
    AppEntry, Config, Defaults, EmailChannel, LogChannel, LlmConfig,
    MobsfConfig, NotificationsConfig, WebSearchConfig,
)
from mobsf_harness.llm.types import LlmResponse, ToolCall
from mobsf_harness.pipeline import run_for_app, PipelineDeps
from mobsf_harness.state import StateStore


def _fake_mobsf(report: dict):
    client = MagicMock()
    client.upload.return_value = "HASH"
    client.scan.return_value = "HASH"
    client.report_json.return_value = report
    return client


def _fake_fetcher(artifact_bytes: bytes = b"APK"):
    fetcher = MagicMock()
    from mobsf_harness.fetchers.base import FetchResult, VersionInfo
    fetcher.latest_version.return_value = VersionInfo("1.0.0", "100")
    def fetch(app, *, version_code, dest_dir):
        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        p = Path(dest_dir) / "artifact.apk"
        p.write_bytes(artifact_bytes)
        return FetchResult(artifact_path=p, sha256="deadbeef", version_name="1.0.0", version_code="100")
    fetcher.fetch.side_effect = fetch
    return fetcher


def _cfg(tmp_path: Path) -> Config:
    return Config(
        defaults=Defaults(),
        mobsf=MobsfConfig(url="http://x", api_key_env="X", api_key="k"),
        llm=LlmConfig(provider="anthropic", model="m", api_key_env="X", api_key="k"),
        web_search=WebSearchConfig(backend="duckduckgo"),
        notifications=NotificationsConfig(log=LogChannel(path=str(tmp_path / "n.jsonl"))),
        policy="",
        apps=[AppEntry(platform="android", package_id="com.e", source="play_store")],
    )


def test_new_app_is_scanned_and_summarized(tmp_path: Path, fixtures_dir: Path, monkeypatch):
    monkeypatch.setenv("X", "k")
    report = json.loads((fixtures_dir / "mobsf" / "small_report.json").read_text())
    state = StateStore(tmp_path / "state.sqlite"); state.initialize()
    deps = PipelineDeps(
        state=state,
        mobsf_client=_fake_mobsf(report),
        fetcher_factory=lambda app: _fake_fetcher(),
        llm_client=FakeLlmClient([
            LlmResponse(
                text="", stop_reason="tool_use",
                usage_input_tokens=0, usage_output_tokens=0,
                tool_calls=[ToolCall(id="c", name="write_summary", arguments={"markdown": "# ok"})],
            ),
            LlmResponse(text="", stop_reason="end_turn",
                        usage_input_tokens=0, usage_output_tokens=0, tool_calls=[]),
        ]),
        reports_root=tmp_path / "reports",
    )
    cfg = _cfg(tmp_path)

    result = run_for_app(deps, cfg, cfg.apps[0])

    assert result.status == "done"
    assert (tmp_path / "reports" / "android" / "com.e" / "1.0.0-100" / "summary.md").exists()
    assert (tmp_path / "reports" / "android" / "com.e" / "1.0.0-100" / "mobsf.json").exists()


def test_unchanged_version_skipped(tmp_path: Path, fixtures_dir: Path, monkeypatch):
    monkeypatch.setenv("X", "k")
    report = json.loads((fixtures_dir / "mobsf" / "small_report.json").read_text())
    state = StateStore(tmp_path / "state.sqlite"); state.initialize()
    app = state.get_or_create_app("android", "com.e", "play_store")
    prior = state.create_scan(app.id, "1.0.0", "100", "h", "reports/x")
    state.update_scan_status(prior.id, "done")

    deps = PipelineDeps(
        state=state,
        mobsf_client=_fake_mobsf(report),
        fetcher_factory=lambda app: _fake_fetcher(),
        llm_client=FakeLlmClient([]),
        reports_root=tmp_path / "reports",
    )
    cfg = _cfg(tmp_path)

    result = run_for_app(deps, cfg, cfg.apps[0])

    assert result.status == "skipped"
    assert result.reason == "unchanged_version"
