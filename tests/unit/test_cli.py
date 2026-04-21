from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from mobsf_harness.cli import main


VALID_YAML = """
defaults: {dynamic_analysis: false, notification_channels: [log]}
mobsf: {url: 'http://x', api_key_env: MOBSF_API_KEY}
llm:
  provider: anthropic
  model: claude-opus-4-7
  api_key_env: ANTHROPIC_API_KEY
web_search: {backend: duckduckgo}
notifications: {log: {path: ./n.jsonl}}
policy: ""
apps:
  - {platform: android, package_id: com.e, source: play_store}
"""


def test_list_prints_empty_when_no_scans(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MOBSF_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    (tmp_path / "apps.yaml").write_text(VALID_YAML)

    r = CliRunner().invoke(main, ["list"])
    assert r.exit_code == 0
    assert "com.e" in r.output


@patch("mobsf_harness.cli.run_for_app")
def test_run_only_filters(mock_run, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MOBSF_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    (tmp_path / "apps.yaml").write_text(VALID_YAML)
    from mobsf_harness.pipeline import PipelineResult
    mock_run.return_value = PipelineResult(status="done")

    r = CliRunner().invoke(main, ["run", "--only", "com.e"])

    assert r.exit_code == 0
    assert mock_run.call_count == 1
