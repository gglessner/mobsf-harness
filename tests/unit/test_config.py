import os
from pathlib import Path

import pytest
import yaml

from mobsf_harness.config import Config, ConfigError, load_config


VALID_YAML = """
defaults:
  dynamic_analysis: false
  notification_channels: [log]

mobsf:
  url: http://localhost:8000
  api_key_env: MOBSF_API_KEY

llm:
  provider: anthropic
  model: claude-opus-4-7
  api_key_env: ANTHROPIC_API_KEY
  max_turns: 12
  max_tokens_per_session: 100000

web_search:
  backend: tavily
  api_key_env: TAVILY_API_KEY

notifications:
  log:
    path: ./notifications.jsonl

policy: "notify on new high severity"

apps:
  - platform: android
    package_id: com.example.app
    source: play_store
"""


def test_load_valid_config(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOBSF_API_KEY", "mob-123")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-456")
    monkeypatch.setenv("TAVILY_API_KEY", "tav-789")
    p = tmp_path / "apps.yaml"
    p.write_text(VALID_YAML)

    cfg = load_config(p)

    assert isinstance(cfg, Config)
    assert cfg.mobsf.url == "http://localhost:8000"
    assert cfg.mobsf.api_key == "mob-123"
    assert cfg.llm.provider == "anthropic"
    assert cfg.llm.api_key == "ant-456"
    assert len(cfg.apps) == 1
    assert cfg.apps[0].platform == "android"
    assert cfg.apps[0].identifier == "com.example.app"
    assert cfg.apps[0].notification_channels == ["log"]


def test_missing_env_var_raises(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MOBSF_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("TAVILY_API_KEY", "x")
    p = tmp_path / "apps.yaml"
    p.write_text(VALID_YAML)

    with pytest.raises(ConfigError, match="MOBSF_API_KEY"):
        load_config(p)


def test_unknown_llm_provider_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOBSF_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("TAVILY_API_KEY", "x")
    bad = VALID_YAML.replace("provider: anthropic", "provider: bogus")
    p = tmp_path / "apps.yaml"
    p.write_text(bad)

    with pytest.raises(ConfigError):
        load_config(p)


def test_openai_compatible_requires_base_url(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOBSF_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("TAVILY_API_KEY", "x")
    data = yaml.safe_load(VALID_YAML)
    data["llm"]["provider"] = "openai-compatible"
    data["llm"]["base_url"] = None
    p = tmp_path / "apps.yaml"
    p.write_text(yaml.safe_dump(data))

    with pytest.raises(ConfigError, match="base_url"):
        load_config(p)


def test_ios_app_with_drop_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOBSF_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("TAVILY_API_KEY", "x")
    data = yaml.safe_load(VALID_YAML)
    data["apps"].append({
        "platform": "ios",
        "bundle_id": "com.example.ios",
        "source": "drop_dir",
        "drop_path": "./drops/ios/com.example.ios/",
    })
    p = tmp_path / "apps.yaml"
    p.write_text(yaml.safe_dump(data))

    cfg = load_config(p)

    assert cfg.apps[1].platform == "ios"
    assert cfg.apps[1].identifier == "com.example.ios"
    assert cfg.apps[1].drop_path == "./drops/ios/com.example.ios/"
