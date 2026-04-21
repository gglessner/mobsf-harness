# MOBSF Agent Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python harness that performs scheduled, automated MOBSF analysis of mobile apps, with a bounded AI agent loop producing summaries and operator-judged notifications.

**Architecture:** Hybrid pipeline — deterministic Python pipeline handles version checks, downloads, MOBSF uploads, and polling; a per-scan bounded tool-use loop handles analysis, summary, and notification judgment. Pluggable LLM providers (Anthropic native, OpenAI-compatible) and pluggable web search (Tavily/Brave/DuckDuckGo).

**Tech Stack:** Python 3.11+, pytest, pydantic v2, httpx, sqlite3, anthropic SDK, openai SDK, click, PyYAML, tenacity, respx (HTTP mocking).

**Spec:** `docs/superpowers/specs/2026-04-20-mobsf-agent-harness-design.md`

---

## File Structure

```
mobsf_harness/
├── __init__.py
├── cli.py                # click entry point
├── config.py             # pydantic schema + loader
├── state.py              # SQLite DAO
├── fetchers/
│   ├── __init__.py       # Fetcher protocol + factory
│   ├── base.py           # FetchResult dataclass, shared helpers
│   ├── play_store.py     # gplaycli wrapper
│   ├── app_store.py      # ipatool wrapper
│   └── drop_dir.py       # manual-drop fallback
├── mobsf_client.py       # HTTPX-based MOBSF REST client
├── llm/
│   ├── __init__.py       # LLMClient protocol + factory
│   ├── types.py          # ToolCall, ToolResult, Message, etc.
│   ├── anthropic_client.py
│   └── openai_client.py  # handles OpenRouter + local OpenAI-compat
├── tools/
│   ├── __init__.py       # Tool registry + schema marshalling
│   ├── types.py          # Tool protocol, ToolSchema
│   ├── report.py         # get_report_section, get_prior_finding_history
│   ├── emit.py           # write_summary, notify
│   └── search/
│       ├── __init__.py   # WebSearch protocol + factory
│       ├── tavily.py
│       ├── brave.py
│       └── duckduckgo.py
├── agent.py              # bounded tool-use loop
├── notifier.py           # log/email/webhook channel router
└── pipeline.py           # per-app orchestrator

tests/
├── conftest.py           # shared fixtures
├── fixtures/
│   ├── mobsf/
│   │   ├── small_report.json
│   │   ├── medium_report.json
│   │   └── large_report.json
│   ├── artifacts/
│   │   └── tiny.apk      # small open-source APK for E2E smoke
│   └── llm_transcripts/
│       ├── happy_path.json
│       └── missing_summary.json
├── unit/
│   ├── test_config.py
│   ├── test_state.py
│   ├── test_fetchers_drop_dir.py
│   ├── test_fetchers_play_store.py
│   ├── test_fetchers_app_store.py
│   ├── test_mobsf_client.py
│   ├── test_llm_anthropic.py
│   ├── test_llm_openai.py
│   ├── test_tools_report.py
│   ├── test_tools_search_*.py
│   ├── test_tools_emit.py
│   ├── test_agent.py
│   └── test_notifier.py
├── integration/
│   └── test_pipeline.py
└── e2e/
    └── test_smoke.py     # gated by MOBSF_HARNESS_E2E=1

pyproject.toml
apps.example.yaml
.gitignore
README.md
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `mobsf_harness/__init__.py`
- Create: `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/conftest.py`
- Create: `.gitignore`
- Create: `apps.example.yaml`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "mobsf-harness"
version = "0.1.0"
description = "Scheduled MOBSF analysis with a bounded AI agent loop"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.6",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "click>=8.1",
    "tenacity>=8.2",
    "anthropic>=0.40",
    "openai>=1.50",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
    "ruff>=0.4",
]

[project.scripts]
mobsf-harness = "mobsf_harness.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
markers = [
    "e2e: end-to-end tests that need real MOBSF and real LLM (MOBSF_HARNESS_E2E=1)",
]

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [ ] **Step 2: Create `mobsf_harness/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/
*.egg-info/
dist/
build/
.ruff_cache/

# Harness state and data
state.sqlite
state.sqlite-journal
reports/
drops/
harness.log
notifications.jsonl

# Local config
apps.yaml
.env
```

- [ ] **Step 4: Create `apps.example.yaml`**

```yaml
defaults:
  dynamic_analysis: false
  notification_channels: [log]

mobsf:
  url: http://localhost:8000
  api_key_env: MOBSF_API_KEY

llm:
  provider: anthropic
  model: claude-opus-4-7
  base_url: null
  api_key_env: ANTHROPIC_API_KEY
  max_turns: 12
  max_tokens_per_session: 100000

web_search:
  backend: tavily
  api_key_env: TAVILY_API_KEY

notifications:
  log:
    path: ./notifications.jsonl

policy: |
  Notify on any NEW high/critical finding, any new exported activity,
  or any new hardcoded secret. Recurring issues are not news.

apps:
  - platform: android
    package_id: com.example.app
    source: play_store
    notification_channels: [log]
```

- [ ] **Step 5: Create empty packages + conftest**

```python
# mobsf_harness/__init__.py   -- already done
# tests/__init__.py            -- empty
# tests/unit/__init__.py       -- empty
# tests/integration/__init__.py -- empty
```

```python
# tests/conftest.py
import pytest
from pathlib import Path

@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
```

- [ ] **Step 6: Install and verify**

Run: `pip install -e '.[dev]' && pytest`
Expected: `0 passed` (no tests yet, no errors).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml mobsf_harness/ tests/ .gitignore apps.example.yaml
git commit -m "feat: project scaffolding"
```

---

## Task 2: Config Schema

**Files:**
- Create: `mobsf_harness/config.py`
- Create: `tests/unit/test_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_config.py
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
    assert cfg.mobsf.api_key == "mob-123"       # resolved from env
    assert cfg.llm.provider == "anthropic"
    assert cfg.llm.api_key == "ant-456"
    assert len(cfg.apps) == 1
    assert cfg.apps[0].platform == "android"
    assert cfg.apps[0].identifier == "com.example.app"
    assert cfg.apps[0].notification_channels == ["log"]  # inherited default


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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_config.py -v`
Expected: FAIL — `mobsf_harness.config` does not exist.

- [ ] **Step 3: Write `mobsf_harness/config.py`**

```python
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator


class ConfigError(Exception):
    """Raised when the harness config is invalid or missing required values."""


class MobsfConfig(BaseModel):
    url: str
    api_key_env: str
    api_key: str = ""          # resolved from env after load

    @model_validator(mode="after")
    def _resolve_key(self) -> "MobsfConfig":
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ValueError(f"env var {self.api_key_env} is not set")
        self.api_key = key
        return self


class LlmConfig(BaseModel):
    provider: Literal["anthropic", "openai-compatible"]
    model: str
    base_url: str | None = None
    api_key_env: str
    api_key: str = ""
    max_turns: int = 12
    max_tokens_per_session: int = 100_000

    @model_validator(mode="after")
    def _validate(self) -> "LlmConfig":
        if self.provider == "openai-compatible" and not self.base_url:
            raise ValueError("llm.base_url is required when provider is openai-compatible")
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ValueError(f"env var {self.api_key_env} is not set")
        self.api_key = key
        return self


class WebSearchConfig(BaseModel):
    backend: Literal["tavily", "brave", "duckduckgo"]
    api_key_env: str | None = None
    api_key: str = ""

    @model_validator(mode="after")
    def _resolve(self) -> "WebSearchConfig":
        if self.backend == "duckduckgo":
            return self
        if not self.api_key_env:
            raise ValueError(f"web_search.api_key_env is required for backend {self.backend}")
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ValueError(f"env var {self.api_key_env} is not set")
        self.api_key = key
        return self


class LogChannel(BaseModel):
    path: str


class EmailChannel(BaseModel):
    smtp_host: str
    smtp_port: int
    from_addr: str
    to_addrs: list[str]
    username_env: str | None = None
    password_env: str | None = None
    username: str = ""
    password: str = ""

    @model_validator(mode="after")
    def _resolve(self) -> "EmailChannel":
        if self.username_env:
            self.username = os.environ.get(self.username_env, "")
        if self.password_env:
            self.password = os.environ.get(self.password_env, "")
        return self


class WebhookChannel(BaseModel):
    url: str
    headers: dict[str, str] = Field(default_factory=dict)


class NotificationsConfig(BaseModel):
    log: LogChannel | None = None
    email: EmailChannel | None = None
    webhook: WebhookChannel | None = None


class Defaults(BaseModel):
    dynamic_analysis: bool = False
    notification_channels: list[str] = Field(default_factory=lambda: ["log"])


class AppEntry(BaseModel):
    platform: Literal["android", "ios"]
    package_id: str | None = None
    bundle_id: str | None = None
    source: Literal["play_store", "app_store", "drop_dir"]
    notification_channels: list[str] | None = None
    dynamic_analysis: bool | None = None
    tags: list[str] = Field(default_factory=list)
    drop_path: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> "AppEntry":
        if self.platform == "android" and not self.package_id:
            raise ValueError("android app requires package_id")
        if self.platform == "ios" and not self.bundle_id:
            raise ValueError("ios app requires bundle_id")
        if self.source == "drop_dir" and not self.drop_path:
            raise ValueError("drop_dir source requires drop_path")
        return self

    @property
    def identifier(self) -> str:
        return self.package_id or self.bundle_id  # type: ignore[return-value]


class Config(BaseModel):
    defaults: Defaults = Field(default_factory=Defaults)
    mobsf: MobsfConfig
    llm: LlmConfig
    web_search: WebSearchConfig
    notifications: NotificationsConfig
    policy: str = ""
    apps: list[AppEntry]

    @model_validator(mode="after")
    def _apply_defaults(self) -> "Config":
        for app in self.apps:
            if app.notification_channels is None:
                app.notification_channels = list(self.defaults.notification_channels)
            if app.dynamic_analysis is None:
                app.dynamic_analysis = self.defaults.dynamic_analysis
        return self


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text())
    try:
        return Config.model_validate(raw)
    except ValidationError as e:
        raise ConfigError(str(e)) from e
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_config.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add mobsf_harness/config.py tests/unit/test_config.py
git commit -m "feat: config schema with pydantic"
```

---

## Task 3: SQLite State Layer

**Files:**
- Create: `mobsf_harness/state.py`
- Create: `tests/unit/test_state.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_state.py
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mobsf_harness.state import (
    AppRecord,
    FindingRecord,
    NotificationRecord,
    ScanRecord,
    StateStore,
)


@pytest.fixture
def store(tmp_path: Path) -> StateStore:
    s = StateStore(tmp_path / "state.sqlite")
    s.initialize()
    return s


def test_get_or_create_app_is_idempotent(store: StateStore):
    a1 = store.get_or_create_app("android", "com.example", "play_store")
    a2 = store.get_or_create_app("android", "com.example", "play_store")
    assert a1.id == a2.id


def test_record_scan_and_fetch_latest(store: StateStore):
    app = store.get_or_create_app("android", "com.example", "play_store")
    scan = store.create_scan(
        app_id=app.id,
        version_name="1.2.3",
        version_code="4501",
        sha256="abc123",
        report_dir="reports/android/com.example/1.2.3-4501",
    )
    assert scan.status == "queued"
    store.update_scan_status(scan.id, "done", finished_at=datetime.now(timezone.utc))

    latest = store.latest_completed_scan(app.id)
    assert latest is not None
    assert latest.version_code == "4501"
    assert latest.status == "done"


def test_latest_completed_scan_skips_failed(store: StateStore):
    app = store.get_or_create_app("android", "com.example", "play_store")
    s1 = store.create_scan(app.id, "1.0", "1", "h1", "r1")
    store.update_scan_status(s1.id, "done", finished_at=datetime.now(timezone.utc))
    s2 = store.create_scan(app.id, "1.1", "2", "h2", "r2")
    store.update_scan_status(s2.id, "failed", error_message="boom")

    latest = store.latest_completed_scan(app.id)
    assert latest.id == s1.id


def test_artifact_hash_is_unique_per_app(store: StateStore):
    app = store.get_or_create_app("android", "com.example", "play_store")
    store.create_scan(app.id, "1.0", "1", "same_hash", "r1")
    with pytest.raises(Exception):
        store.create_scan(app.id, "1.1", "2", "same_hash", "r2")


def test_findings_roundtrip(store: StateStore):
    app = store.get_or_create_app("android", "com.example", "play_store")
    scan = store.create_scan(app.id, "1.0", "1", "h", "r")
    store.add_finding(scan.id, "RULE_A@MainActivity", "high", "exported", {"raw": 1})
    store.add_finding(scan.id, "RULE_B@Foo", "medium", "tls", {"raw": 2})

    found = store.findings_for_scan(scan.id)
    assert len(found) == 2
    assert {f.finding_key for f in found} == {"RULE_A@MainActivity", "RULE_B@Foo"}


def test_prior_finding_history(store: StateStore):
    app = store.get_or_create_app("android", "com.example", "play_store")
    older = store.create_scan(app.id, "1.0", "1", "h1", "r1")
    store.update_scan_status(older.id, "done", finished_at=datetime.now(timezone.utc))
    store.add_finding(older.id, "RULE_A", "high", "t", {})
    newer = store.create_scan(app.id, "1.1", "2", "h2", "r2")
    store.update_scan_status(newer.id, "done", finished_at=datetime.now(timezone.utc))

    history = store.prior_finding_history(app.id, "RULE_A", before_scan_id=newer.id)

    assert len(history) == 1
    assert history[0].scan_id == older.id


def test_record_notification(store: StateStore):
    app = store.get_or_create_app("android", "com.example", "play_store")
    scan = store.create_scan(app.id, "1.0", "1", "h", "r")
    n = store.record_notification(scan.id, "log", "high", "saw new issue")
    assert n.sent_at is None
    store.mark_notification_sent(n.id)
    refetched = store.notifications_for_scan(scan.id)[0]
    assert refetched.sent_at is not None
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_state.py -v`
Expected: FAIL — `mobsf_harness.state` not found.

- [ ] **Step 3: Write `mobsf_harness/state.py`**

```python
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS apps (
  id INTEGER PRIMARY KEY,
  platform TEXT NOT NULL,
  identifier TEXT NOT NULL,
  source TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  last_checked TEXT,
  UNIQUE(platform, identifier)
);

CREATE TABLE IF NOT EXISTS scans (
  id INTEGER PRIMARY KEY,
  app_id INTEGER NOT NULL REFERENCES apps(id),
  version_name TEXT,
  version_code TEXT,
  sha256 TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  error_message TEXT,
  report_dir TEXT,
  mobsf_scan_hash TEXT,
  UNIQUE(app_id, sha256)
);

CREATE TABLE IF NOT EXISTS findings (
  id INTEGER PRIMARY KEY,
  scan_id INTEGER NOT NULL REFERENCES scans(id),
  finding_key TEXT NOT NULL,
  severity TEXT NOT NULL,
  title TEXT NOT NULL,
  raw TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_findings_scan ON findings(scan_id);
CREATE INDEX IF NOT EXISTS idx_findings_key ON findings(finding_key);

CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY,
  scan_id INTEGER NOT NULL REFERENCES scans(id),
  channel TEXT NOT NULL,
  severity TEXT NOT NULL,
  body TEXT NOT NULL,
  sent_at TEXT,
  error_message TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AppRecord:
    id: int
    platform: str
    identifier: str
    source: str
    first_seen: str
    last_checked: str | None


@dataclass
class ScanRecord:
    id: int
    app_id: int
    version_name: str | None
    version_code: str | None
    sha256: str
    started_at: str
    finished_at: str | None
    status: str
    error_message: str | None
    report_dir: str | None
    mobsf_scan_hash: str | None


@dataclass
class FindingRecord:
    id: int
    scan_id: int
    finding_key: str
    severity: str
    title: str
    raw: dict[str, Any]


@dataclass
class NotificationRecord:
    id: int
    scan_id: int
    channel: str
    severity: str
    body: str
    sent_at: str | None
    error_message: str | None


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.row_factory = sqlite3.Row

    def initialize(self) -> None:
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # ---- apps ----
    def get_or_create_app(self, platform: str, identifier: str, source: str) -> AppRecord:
        row = self._conn.execute(
            "SELECT * FROM apps WHERE platform=? AND identifier=?",
            (platform, identifier),
        ).fetchone()
        if row is not None:
            return self._app(row)
        cur = self._conn.execute(
            "INSERT INTO apps(platform, identifier, source, first_seen) VALUES (?,?,?,?)",
            (platform, identifier, source, _now()),
        )
        row = self._conn.execute("SELECT * FROM apps WHERE id=?", (cur.lastrowid,)).fetchone()
        return self._app(row)

    def touch_app(self, app_id: int) -> None:
        self._conn.execute("UPDATE apps SET last_checked=? WHERE id=?", (_now(), app_id))

    # ---- scans ----
    def create_scan(
        self,
        app_id: int,
        version_name: str | None,
        version_code: str | None,
        sha256: str,
        report_dir: str,
    ) -> ScanRecord:
        cur = self._conn.execute(
            "INSERT INTO scans(app_id, version_name, version_code, sha256, started_at, status, report_dir) "
            "VALUES (?,?,?,?,?,?,?)",
            (app_id, version_name, version_code, sha256, _now(), "queued", report_dir),
        )
        row = self._conn.execute("SELECT * FROM scans WHERE id=?", (cur.lastrowid,)).fetchone()
        return self._scan(row)

    def update_scan_status(
        self,
        scan_id: int,
        status: str,
        *,
        finished_at: datetime | None = None,
        error_message: str | None = None,
        mobsf_scan_hash: str | None = None,
    ) -> None:
        self._conn.execute(
            "UPDATE scans SET status=?, finished_at=COALESCE(?, finished_at), "
            "error_message=COALESCE(?, error_message), mobsf_scan_hash=COALESCE(?, mobsf_scan_hash) "
            "WHERE id=?",
            (
                status,
                finished_at.isoformat() if finished_at else None,
                error_message,
                mobsf_scan_hash,
                scan_id,
            ),
        )

    def latest_completed_scan(self, app_id: int) -> ScanRecord | None:
        row = self._conn.execute(
            "SELECT * FROM scans WHERE app_id=? AND status='done' ORDER BY id DESC LIMIT 1",
            (app_id,),
        ).fetchone()
        return self._scan(row) if row else None

    def get_scan(self, scan_id: int) -> ScanRecord | None:
        row = self._conn.execute("SELECT * FROM scans WHERE id=?", (scan_id,)).fetchone()
        return self._scan(row) if row else None

    # ---- findings ----
    def add_finding(
        self,
        scan_id: int,
        finding_key: str,
        severity: str,
        title: str,
        raw: dict[str, Any],
    ) -> None:
        self._conn.execute(
            "INSERT INTO findings(scan_id, finding_key, severity, title, raw) VALUES (?,?,?,?,?)",
            (scan_id, finding_key, severity, title, json.dumps(raw)),
        )

    def findings_for_scan(self, scan_id: int) -> list[FindingRecord]:
        rows = self._conn.execute(
            "SELECT * FROM findings WHERE scan_id=? ORDER BY id", (scan_id,)
        ).fetchall()
        return [self._finding(r) for r in rows]

    def prior_finding_history(
        self, app_id: int, finding_key: str, *, before_scan_id: int, limit: int = 5
    ) -> list[FindingRecord]:
        rows = self._conn.execute(
            """SELECT f.* FROM findings f
               JOIN scans s ON f.scan_id = s.id
               WHERE s.app_id=? AND f.finding_key=? AND f.scan_id < ?
               ORDER BY f.scan_id DESC LIMIT ?""",
            (app_id, finding_key, before_scan_id, limit),
        ).fetchall()
        return [self._finding(r) for r in rows]

    # ---- notifications ----
    def record_notification(
        self, scan_id: int, channel: str, severity: str, body: str
    ) -> NotificationRecord:
        cur = self._conn.execute(
            "INSERT INTO notifications(scan_id, channel, severity, body) VALUES (?,?,?,?)",
            (scan_id, channel, severity, body),
        )
        row = self._conn.execute(
            "SELECT * FROM notifications WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        return self._notification(row)

    def mark_notification_sent(self, notification_id: int) -> None:
        self._conn.execute(
            "UPDATE notifications SET sent_at=? WHERE id=?", (_now(), notification_id)
        )

    def mark_notification_failed(self, notification_id: int, error: str) -> None:
        self._conn.execute(
            "UPDATE notifications SET error_message=? WHERE id=?", (error, notification_id)
        )

    def notifications_for_scan(self, scan_id: int) -> list[NotificationRecord]:
        rows = self._conn.execute(
            "SELECT * FROM notifications WHERE scan_id=? ORDER BY id", (scan_id,)
        ).fetchall()
        return [self._notification(r) for r in rows]

    # ---- row mappers ----
    @staticmethod
    def _app(row: sqlite3.Row) -> AppRecord:
        return AppRecord(**dict(row))

    @staticmethod
    def _scan(row: sqlite3.Row) -> ScanRecord:
        return ScanRecord(**dict(row))

    @staticmethod
    def _finding(row: sqlite3.Row) -> FindingRecord:
        d = dict(row)
        d["raw"] = json.loads(d["raw"])
        return FindingRecord(**d)

    @staticmethod
    def _notification(row: sqlite3.Row) -> NotificationRecord:
        return NotificationRecord(**dict(row))
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_state.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add mobsf_harness/state.py tests/unit/test_state.py
git commit -m "feat: sqlite state layer"
```

---

## Task 4: MOBSF REST Client

**Files:**
- Create: `mobsf_harness/mobsf_client.py`
- Create: `tests/fixtures/mobsf/small_report.json` (representative report)
- Create: `tests/unit/test_mobsf_client.py`

MOBSF REST endpoints (v4+):
- `POST /api/v1/upload` (multipart file + `Authorization: <api_key>`) → `{hash, scan_type, file_name}`
- `POST /api/v1/scan` (`hash`, `re_scan=0/1`) → scan result (may take time)
- `POST /api/v1/report_json` (`hash`) → full JSON report
- `POST /api/v1/download_pdf` (`hash`) → PDF bytes

- [ ] **Step 1: Create minimal report fixture**

`tests/fixtures/mobsf/small_report.json` — a small representative MOBSF JSON document. Content:

```json
{
  "app_name": "com.example.app",
  "version_name": "1.2.3",
  "version_code": "4501",
  "file_name": "com.example.app.apk",
  "hash": "aaaa1111bbbb2222",
  "size": "12.3MB",
  "sha256": "abc123",
  "severity": {"high": 1, "medium": 2, "low": 3, "info": 4},
  "permissions": {"android.permission.INTERNET": {"status": "normal"}},
  "manifest_analysis": {"manifest_findings": []},
  "code_analysis": {"findings": {}},
  "network_security": {"network_findings": []},
  "secrets": []
}
```

- [ ] **Step 2: Write failing tests**

```python
# tests/unit/test_mobsf_client.py
import json
from pathlib import Path

import httpx
import pytest
import respx

from mobsf_harness.mobsf_client import MobsfClient, MobsfError, ScanStatus


@pytest.fixture
def client() -> MobsfClient:
    return MobsfClient(base_url="http://mobsf.test", api_key="k")


@respx.mock
def test_upload_returns_hash(client: MobsfClient, tmp_path: Path):
    respx.post("http://mobsf.test/api/v1/upload").mock(
        return_value=httpx.Response(200, json={"hash": "h123", "scan_type": "apk", "file_name": "x.apk"})
    )
    apk = tmp_path / "x.apk"
    apk.write_bytes(b"PK\x03\x04")

    hsh = client.upload(apk)

    assert hsh == "h123"


@respx.mock
def test_upload_auth_failure_raises(client: MobsfClient, tmp_path: Path):
    respx.post("http://mobsf.test/api/v1/upload").mock(return_value=httpx.Response(401))
    apk = tmp_path / "x.apk"
    apk.write_bytes(b"x")

    with pytest.raises(MobsfError, match="401"):
        client.upload(apk)


@respx.mock
def test_scan_triggers_and_returns_hash(client: MobsfClient):
    respx.post("http://mobsf.test/api/v1/scan").mock(
        return_value=httpx.Response(200, json={"status": "success"})
    )
    # Scan is fire-and-forget in MOBSF; client returns the hash it was given
    result = client.scan("h123")
    assert result == "h123"


@respx.mock
def test_report_json_roundtrip(client: MobsfClient, fixtures_dir):
    report = json.loads((fixtures_dir / "mobsf" / "small_report.json").read_text())
    respx.post("http://mobsf.test/api/v1/report_json").mock(
        return_value=httpx.Response(200, json=report)
    )

    got = client.report_json("h123")

    assert got["app_name"] == "com.example.app"


@respx.mock
def test_download_pdf_writes_file(client: MobsfClient, tmp_path: Path):
    respx.post("http://mobsf.test/api/v1/download_pdf").mock(
        return_value=httpx.Response(200, content=b"%PDF-1.4 ...")
    )
    out = tmp_path / "r.pdf"

    client.download_pdf("h123", out)

    assert out.read_bytes().startswith(b"%PDF")


@respx.mock
def test_transient_5xx_retried(client: MobsfClient, tmp_path: Path):
    route = respx.post("http://mobsf.test/api/v1/upload").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, json={"hash": "ok", "scan_type": "apk", "file_name": "x"}),
        ]
    )
    apk = tmp_path / "x.apk"
    apk.write_bytes(b"x")

    assert client.upload(apk) == "ok"
    assert route.call_count == 3
```

- [ ] **Step 3: Run tests to verify failure**

Run: `pytest tests/unit/test_mobsf_client.py -v`
Expected: FAIL — module not found.

- [ ] **Step 4: Write `mobsf_harness/mobsf_client.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


class MobsfError(Exception):
    pass


@dataclass
class ScanStatus:
    hash: str
    file_name: str
    scan_type: str


def _retriable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return 500 <= exc.response.status_code < 600
    return isinstance(exc, httpx.TransportError)


_retry = retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=4),
    reraise=True,
)


class MobsfClient:
    """Thin REST client for MOBSF v4+."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 60.0) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": api_key}
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "MobsfClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    # ---- ops ----
    def upload(self, path: Path) -> str:
        return self._upload_once(path)

    def scan(self, hash_: str, *, re_scan: bool = False) -> str:
        self._post(
            "/api/v1/scan",
            data={"hash": hash_, "re_scan": "1" if re_scan else "0"},
        )
        return hash_

    def report_json(self, hash_: str) -> dict[str, Any]:
        return self._post("/api/v1/report_json", data={"hash": hash_}).json()

    def download_pdf(self, hash_: str, out_path: Path) -> None:
        resp = self._post("/api/v1/download_pdf", data={"hash": hash_})
        Path(out_path).write_bytes(resp.content)

    # ---- internals ----
    @_retry
    def _upload_once(self, path: Path) -> str:
        with path.open("rb") as fp:
            resp = self._client.post(
                f"{self._base}/api/v1/upload",
                headers=self._headers,
                files={"file": (path.name, fp, "application/octet-stream")},
            )
        self._raise_for_status(resp)
        return resp.json()["hash"]

    @_retry
    def _post(self, endpoint: str, *, data: dict[str, str]) -> httpx.Response:
        resp = self._client.post(
            f"{self._base}{endpoint}",
            headers=self._headers,
            data=data,
        )
        self._raise_for_status(resp)
        return resp

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            if 500 <= resp.status_code < 600:
                raise httpx.HTTPStatusError(
                    f"{resp.status_code}", request=resp.request, response=resp
                )
            raise MobsfError(f"MOBSF returned {resp.status_code}: {resp.text[:200]}")
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/unit/test_mobsf_client.py -v`
Expected: all pass (6 tests).

- [ ] **Step 6: Commit**

```bash
git add mobsf_harness/mobsf_client.py tests/unit/test_mobsf_client.py tests/fixtures/mobsf/small_report.json
git commit -m "feat: MOBSF REST client"
```

---

## Task 5: Fetcher Protocol + Drop-Dir Fetcher

**Files:**
- Create: `mobsf_harness/fetchers/__init__.py`
- Create: `mobsf_harness/fetchers/base.py`
- Create: `mobsf_harness/fetchers/drop_dir.py`
- Create: `tests/unit/test_fetchers_drop_dir.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_fetchers_drop_dir.py
import hashlib
from pathlib import Path

import pytest

from mobsf_harness.config import AppEntry
from mobsf_harness.fetchers.drop_dir import DropDirFetcher
from mobsf_harness.fetchers.base import FetchError


def _app(tmp_path: Path) -> AppEntry:
    return AppEntry(
        platform="ios",
        bundle_id="com.example.ios",
        source="drop_dir",
        drop_path=str(tmp_path / "drop"),
    )


def test_latest_version_picks_highest_version_dir(tmp_path: Path):
    drop = tmp_path / "drop"
    (drop / "1.0.0-100").mkdir(parents=True)
    (drop / "1.1.0-110").mkdir()
    (drop / "2.0.0-200").mkdir()
    (drop / "2.0.0-200" / "app.ipa").write_bytes(b"ipa")

    fetcher = DropDirFetcher()
    latest = fetcher.latest_version(_app(tmp_path))

    assert latest.version_name == "2.0.0"
    assert latest.version_code == "200"


def test_fetch_copies_artifact_and_hashes(tmp_path: Path):
    drop = tmp_path / "drop"
    (drop / "1.0.0-100").mkdir(parents=True)
    payload = b"fake ipa bytes"
    (drop / "1.0.0-100" / "app.ipa").write_bytes(payload)

    fetcher = DropDirFetcher()
    out_dir = tmp_path / "out"
    result = fetcher.fetch(_app(tmp_path), version_code="100", dest_dir=out_dir)

    assert result.artifact_path.read_bytes() == payload
    assert result.sha256 == hashlib.sha256(payload).hexdigest()
    assert result.version_name == "1.0.0"


def test_missing_drop_path_raises(tmp_path: Path):
    fetcher = DropDirFetcher()
    with pytest.raises(FetchError):
        fetcher.latest_version(_app(tmp_path))
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_fetchers_drop_dir.py -v`
Expected: FAIL — modules not found.

- [ ] **Step 3: Write `mobsf_harness/fetchers/base.py`**

```python
from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from mobsf_harness.config import AppEntry


class FetchError(Exception):
    pass


@dataclass
class VersionInfo:
    version_name: str
    version_code: str


@dataclass
class FetchResult:
    artifact_path: Path
    sha256: str
    version_name: str
    version_code: str


class Fetcher(Protocol):
    def latest_version(self, app: AppEntry) -> VersionInfo: ...
    def fetch(self, app: AppEntry, *, version_code: str, dest_dir: Path) -> FetchResult: ...


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_to(src: Path, dest_dir: Path, filename: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dst = dest_dir / filename
    shutil.copy2(src, dst)
    return dst
```

- [ ] **Step 4: Write `mobsf_harness/fetchers/drop_dir.py`**

```python
from __future__ import annotations

import re
from pathlib import Path

from mobsf_harness.config import AppEntry

from .base import FetchError, FetchResult, Fetcher, VersionInfo, copy_to, sha256_file


_VERSION_DIR = re.compile(r"^(?P<name>[^-]+)-(?P<code>\d+)$")
_ARTIFACT_EXTS = (".apk", ".ipa")


def _version_dirs(root: Path) -> list[tuple[Path, VersionInfo]]:
    if not root.exists():
        raise FetchError(f"drop path does not exist: {root}")
    out: list[tuple[Path, VersionInfo]] = []
    for p in root.iterdir():
        if not p.is_dir():
            continue
        m = _VERSION_DIR.match(p.name)
        if m:
            out.append((p, VersionInfo(m["name"], m["code"])))
    if not out:
        raise FetchError(f"no <version>-<code> subdirs found in {root}")
    return out


def _first_artifact(d: Path) -> Path:
    for child in d.iterdir():
        if child.suffix.lower() in _ARTIFACT_EXTS:
            return child
    raise FetchError(f"no .apk or .ipa found in {d}")


class DropDirFetcher:
    def latest_version(self, app: AppEntry) -> VersionInfo:
        root = Path(app.drop_path)  # type: ignore[arg-type]
        dirs = _version_dirs(root)
        dirs.sort(key=lambda item: int(item[1].version_code), reverse=True)
        return dirs[0][1]

    def fetch(self, app: AppEntry, *, version_code: str, dest_dir: Path) -> FetchResult:
        root = Path(app.drop_path)  # type: ignore[arg-type]
        for p, info in _version_dirs(root):
            if info.version_code == version_code:
                src = _first_artifact(p)
                out = copy_to(src, dest_dir, "artifact" + src.suffix.lower())
                return FetchResult(
                    artifact_path=out,
                    sha256=sha256_file(out),
                    version_name=info.version_name,
                    version_code=info.version_code,
                )
        raise FetchError(f"version {version_code} not found in drop dir {root}")
```

- [ ] **Step 5: Write `mobsf_harness/fetchers/__init__.py`**

```python
from __future__ import annotations

from mobsf_harness.config import AppEntry

from .app_store import AppStoreFetcher
from .base import FetchError, FetchResult, Fetcher, VersionInfo
from .drop_dir import DropDirFetcher
from .play_store import PlayStoreFetcher


def fetcher_for(app: AppEntry) -> Fetcher:
    if app.source == "drop_dir":
        return DropDirFetcher()
    if app.source == "play_store":
        return PlayStoreFetcher()
    if app.source == "app_store":
        return AppStoreFetcher()
    raise FetchError(f"unknown source: {app.source}")


__all__ = [
    "AppStoreFetcher",
    "DropDirFetcher",
    "PlayStoreFetcher",
    "FetchError",
    "FetchResult",
    "Fetcher",
    "VersionInfo",
    "fetcher_for",
]
```

Create stubs so `__init__.py` imports cleanly; tasks 6 + 7 flesh them out:

```python
# mobsf_harness/fetchers/play_store.py   (stub — task 6 implements)
from pathlib import Path
from mobsf_harness.config import AppEntry
from .base import FetchError, FetchResult, VersionInfo

class PlayStoreFetcher:
    def latest_version(self, app: AppEntry) -> VersionInfo:
        raise FetchError("PlayStoreFetcher not implemented yet")
    def fetch(self, app: AppEntry, *, version_code: str, dest_dir: Path) -> FetchResult:
        raise FetchError("PlayStoreFetcher not implemented yet")
```

```python
# mobsf_harness/fetchers/app_store.py   (stub — task 7 implements)
from pathlib import Path
from mobsf_harness.config import AppEntry
from .base import FetchError, FetchResult, VersionInfo

class AppStoreFetcher:
    def latest_version(self, app: AppEntry) -> VersionInfo:
        raise FetchError("AppStoreFetcher not implemented yet")
    def fetch(self, app: AppEntry, *, version_code: str, dest_dir: Path) -> FetchResult:
        raise FetchError("AppStoreFetcher not implemented yet")
```

- [ ] **Step 6: Run tests to verify pass**

Run: `pytest tests/unit/test_fetchers_drop_dir.py -v`
Expected: all pass (3 tests).

- [ ] **Step 7: Commit**

```bash
git add mobsf_harness/fetchers/ tests/unit/test_fetchers_drop_dir.py
git commit -m "feat: fetcher protocol + drop-dir fetcher"
```

---

## Task 6: Play Store Fetcher

**Files:**
- Modify: `mobsf_harness/fetchers/play_store.py` (replace stub)
- Create: `tests/unit/test_fetchers_play_store.py`

Strategy: wrap `gplaycli` as a subprocess. For `latest_version`, invoke `gplaycli -s <package_id>` (search) and parse output. For `fetch`, invoke `gplaycli -d <package_id> -f <dest>`. We'll mock `subprocess.run` rather than actually call gplaycli.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_fetchers_play_store.py
import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from mobsf_harness.config import AppEntry
from mobsf_harness.fetchers.base import FetchError
from mobsf_harness.fetchers.play_store import PlayStoreFetcher


def _app() -> AppEntry:
    return AppEntry(platform="android", package_id="com.example.app", source="play_store")


@patch("mobsf_harness.fetchers.play_store.subprocess.run")
def test_latest_version_parses_gplaycli_output(mock_run):
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = (
        "Title | Creator | Size | Downloads | Last Update | Version (Code) | AppID\n"
        "Example App | ExampleCo | 10M | 1000+ | 2026-03-01 | 1.2.3 (4501) | com.example.app\n"
    )

    info = PlayStoreFetcher().latest_version(_app())

    assert info.version_name == "1.2.3"
    assert info.version_code == "4501"


@patch("mobsf_harness.fetchers.play_store.subprocess.run")
def test_latest_version_raises_on_nonzero(mock_run):
    mock_run.return_value.returncode = 1
    mock_run.return_value.stdout = ""
    mock_run.return_value.stderr = "not found"

    with pytest.raises(FetchError, match="not found"):
        PlayStoreFetcher().latest_version(_app())


@patch("mobsf_harness.fetchers.play_store.subprocess.run")
def test_fetch_uses_gplaycli_download_and_hashes(mock_run, tmp_path: Path):
    # simulate gplaycli dropping an apk into the dest directory
    def fake_run(cmd, **kw):
        dest = Path(cmd[cmd.index("-f") + 1])
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "com.example.app.apk").write_bytes(b"APK")
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()
    mock_run.side_effect = fake_run

    out = tmp_path / "out"
    result = PlayStoreFetcher().fetch(_app(), version_code="4501", dest_dir=out)

    assert result.artifact_path.read_bytes() == b"APK"
    assert result.sha256 == hashlib.sha256(b"APK").hexdigest()
    assert result.version_code == "4501"


@patch("mobsf_harness.fetchers.play_store.subprocess.run")
def test_fetch_raises_when_no_apk_produced(mock_run, tmp_path: Path):
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = ""
    mock_run.return_value.stderr = ""
    with pytest.raises(FetchError, match="no .apk"):
        PlayStoreFetcher().fetch(_app(), version_code="x", dest_dir=tmp_path / "out")
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_fetchers_play_store.py -v`
Expected: FAIL — `PlayStoreFetcher not implemented yet`.

- [ ] **Step 3: Replace `mobsf_harness/fetchers/play_store.py`**

```python
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from mobsf_harness.config import AppEntry

from .base import FetchError, FetchResult, Fetcher, VersionInfo, sha256_file


# gplaycli -s prints a table row like:
# "Example App | ExampleCo | 10M | ... | 1.2.3 (4501) | com.example.app"
_VERSION_RE = re.compile(r"(?P<name>[\w\.\-]+)\s*\((?P<code>\d+)\)")


class PlayStoreFetcher:
    def latest_version(self, app: AppEntry) -> VersionInfo:
        proc = subprocess.run(
            ["gplaycli", "-s", app.identifier],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise FetchError(f"gplaycli search failed: {proc.stderr.strip() or proc.stdout.strip()}")
        for line in proc.stdout.splitlines():
            if app.identifier in line:
                m = _VERSION_RE.search(line)
                if m:
                    return VersionInfo(m["name"], m["code"])
        raise FetchError(f"could not parse version for {app.identifier} from gplaycli output")

    def fetch(self, app: AppEntry, *, version_code: str, dest_dir: Path) -> FetchResult:
        dest_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["gplaycli", "-d", app.identifier, "-f", str(dest_dir)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise FetchError(f"gplaycli download failed: {proc.stderr.strip()}")
        apks = list(dest_dir.glob("*.apk"))
        if not apks:
            raise FetchError(f"no .apk produced in {dest_dir}")
        src = apks[0]
        out = dest_dir / "artifact.apk"
        if src != out:
            shutil.move(str(src), out)
        # gplaycli doesn't emit version_name directly on download; trust caller's version_code,
        # re-query version_name via search so the record has both.
        try:
            info = self.latest_version(app)
            version_name = info.version_name
        except FetchError:
            version_name = version_code  # degraded fallback
        return FetchResult(
            artifact_path=out,
            sha256=sha256_file(out),
            version_name=version_name,
            version_code=version_code,
        )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_fetchers_play_store.py -v`
Expected: 4 pass.

- [ ] **Step 5: Commit**

```bash
git add mobsf_harness/fetchers/play_store.py tests/unit/test_fetchers_play_store.py
git commit -m "feat: Play Store fetcher (gplaycli wrapper)"
```

---

## Task 7: App Store Fetcher

**Files:**
- Modify: `mobsf_harness/fetchers/app_store.py` (replace stub)
- Create: `tests/unit/test_fetchers_app_store.py`

Strategy: wrap `ipatool`. `ipatool search <bundle> --limit 1 --format json` returns `{"apps":[{"version":"1.2","bundleID":"..."}]}`. `ipatool download -b <bundle> -o <path>` downloads the IPA. `ipatool` has no `version_code` concept on iOS; we use `version_name` for both fields.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_fetchers_app_store.py
import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from mobsf_harness.config import AppEntry
from mobsf_harness.fetchers.app_store import AppStoreFetcher
from mobsf_harness.fetchers.base import FetchError


def _app() -> AppEntry:
    return AppEntry(platform="ios", bundle_id="com.example.ios", source="app_store")


@patch("mobsf_harness.fetchers.app_store.subprocess.run")
def test_latest_version_parses_ipatool_json(mock_run):
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = (
        '{"apps":[{"bundleID":"com.example.ios","version":"3.4.5"}]}'
    )

    info = AppStoreFetcher().latest_version(_app())

    assert info.version_name == "3.4.5"
    assert info.version_code == "3.4.5"     # iOS has no separate code


@patch("mobsf_harness.fetchers.app_store.subprocess.run")
def test_latest_version_raises_when_no_app(mock_run):
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = '{"apps":[]}'
    with pytest.raises(FetchError):
        AppStoreFetcher().latest_version(_app())


@patch("mobsf_harness.fetchers.app_store.subprocess.run")
def test_fetch_downloads_and_hashes(mock_run, tmp_path: Path):
    def fake_run(cmd, **kw):
        # ipatool download writes the IPA to -o <path>
        if "download" in cmd:
            out_idx = cmd.index("-o") + 1
            Path(cmd[out_idx]).write_bytes(b"IPA")
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()
    mock_run.side_effect = fake_run

    out = tmp_path / "out"
    result = AppStoreFetcher().fetch(_app(), version_code="3.4.5", dest_dir=out)

    assert result.artifact_path.read_bytes() == b"IPA"
    assert result.sha256 == hashlib.sha256(b"IPA").hexdigest()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_fetchers_app_store.py -v`
Expected: FAIL — stub raises.

- [ ] **Step 3: Replace `mobsf_harness/fetchers/app_store.py`**

```python
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from mobsf_harness.config import AppEntry

from .base import FetchError, FetchResult, Fetcher, VersionInfo, sha256_file


class AppStoreFetcher:
    def latest_version(self, app: AppEntry) -> VersionInfo:
        proc = subprocess.run(
            ["ipatool", "search", app.identifier, "--limit", "1", "--format", "json"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise FetchError(f"ipatool search failed: {proc.stderr.strip()}")
        try:
            data = json.loads(proc.stdout)
            apps = data.get("apps", [])
            if not apps:
                raise FetchError(f"no app found for bundle {app.identifier}")
            version = apps[0]["version"]
            return VersionInfo(version_name=version, version_code=version)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            raise FetchError(f"cannot parse ipatool output: {e}") from e

    def fetch(self, app: AppEntry, *, version_code: str, dest_dir: Path) -> FetchResult:
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = dest_dir / "artifact.ipa"
        proc = subprocess.run(
            ["ipatool", "download", "-b", app.identifier, "-o", str(out), "--format", "json"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise FetchError(f"ipatool download failed: {proc.stderr.strip()}")
        if not out.exists():
            raise FetchError(f"ipatool did not produce {out}")
        return FetchResult(
            artifact_path=out,
            sha256=sha256_file(out),
            version_name=version_code,
            version_code=version_code,
        )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_fetchers_app_store.py -v`
Expected: 3 pass.

- [ ] **Step 5: Commit**

```bash
git add mobsf_harness/fetchers/app_store.py tests/unit/test_fetchers_app_store.py
git commit -m "feat: App Store fetcher (ipatool wrapper)"
```

---

## Task 8: LLM Protocol + Types

**Files:**
- Create: `mobsf_harness/llm/__init__.py`
- Create: `mobsf_harness/llm/types.py`

- [ ] **Step 1: Write `mobsf_harness/llm/types.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass
class ToolSchema:
    """Provider-agnostic tool description."""
    name: str
    description: str
    parameters: dict[str, Any]          # JSON Schema for the arguments


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    call_id: str
    content: str                        # serialized JSON or plain text


@dataclass
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""                   # text content
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)


@dataclass
class LlmResponse:
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str                    # "end_turn" | "tool_use" | "max_tokens" | ...
    usage_input_tokens: int
    usage_output_tokens: int


class LlmClient(Protocol):
    def chat(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSchema],
        model: str,
        max_output_tokens: int = 4096,
    ) -> LlmResponse: ...
```

- [ ] **Step 2: Write `mobsf_harness/llm/__init__.py`**

```python
from __future__ import annotations

from mobsf_harness.config import LlmConfig

from .anthropic_client import AnthropicClient
from .openai_client import OpenAICompatibleClient
from .types import LlmClient, LlmResponse, Message, ToolCall, ToolResult, ToolSchema


def make_client(cfg: LlmConfig) -> LlmClient:
    if cfg.provider == "anthropic":
        return AnthropicClient(api_key=cfg.api_key)
    if cfg.provider == "openai-compatible":
        return OpenAICompatibleClient(api_key=cfg.api_key, base_url=cfg.base_url or "")
    raise ValueError(f"unknown llm provider: {cfg.provider}")


__all__ = [
    "AnthropicClient",
    "LlmClient",
    "LlmResponse",
    "Message",
    "OpenAICompatibleClient",
    "ToolCall",
    "ToolResult",
    "ToolSchema",
    "make_client",
]
```

Provide stub implementations so imports resolve; tasks 9 and 10 flesh them out:

```python
# mobsf_harness/llm/anthropic_client.py  (stub)
from .types import LlmResponse, Message, ToolSchema
class AnthropicClient:
    def __init__(self, api_key: str) -> None: self._key = api_key
    def chat(self, *, system, messages, tools, model, max_output_tokens=4096) -> LlmResponse:
        raise NotImplementedError
```

```python
# mobsf_harness/llm/openai_client.py  (stub)
from .types import LlmResponse, Message, ToolSchema
class OpenAICompatibleClient:
    def __init__(self, api_key: str, base_url: str) -> None:
        self._key = api_key
        self._base = base_url
    def chat(self, *, system, messages, tools, model, max_output_tokens=4096) -> LlmResponse:
        raise NotImplementedError
```

- [ ] **Step 3: Commit**

```bash
git add mobsf_harness/llm/
git commit -m "feat: LLM protocol and types"
```

---

## Task 9: Anthropic LLM Client

**Files:**
- Modify: `mobsf_harness/llm/anthropic_client.py` (replace stub)
- Create: `tests/unit/test_llm_anthropic.py`

The Anthropic SDK takes `tools=[{"name","description","input_schema"}]` and returns responses with `content` blocks of type `text` and `tool_use`. Tool results go back in the next user message as `{"type":"tool_result","tool_use_id":..., "content":...}`.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_llm_anthropic.py
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
    # Arrange: SDK returns one text block and one tool_use block
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
    # assistant message should carry tool_use block
    assert sent[1]["role"] == "assistant"
    assert any(b["type"] == "tool_use" and b["id"] == "c1" for b in sent[1]["content"])
    # tool results go in a user-role message with tool_result blocks
    assert sent[2]["role"] == "user"
    assert sent[2]["content"][0]["type"] == "tool_result"
    assert sent[2]["content"][0]["tool_use_id"] == "c1"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_llm_anthropic.py -v`
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Replace `mobsf_harness/llm/anthropic_client.py`**

```python
from __future__ import annotations

from typing import Any

from anthropic import Anthropic

from .types import LlmResponse, Message, ToolCall, ToolResult, ToolSchema


class AnthropicClient:
    def __init__(self, api_key: str) -> None:
        self._sdk = Anthropic(api_key=api_key)

    def chat(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSchema],
        model: str,
        max_output_tokens: int = 4096,
    ) -> LlmResponse:
        sdk_messages = [self._to_sdk_message(m) for m in messages if m.role != "system"]
        sdk_tools = [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in tools
        ]
        rsp = self._sdk.messages.create(
            model=model,
            max_tokens=max_output_tokens,
            system=system,
            tools=sdk_tools,
            messages=sdk_messages,
        )
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in rsp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input)))
        return LlmResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=rsp.stop_reason,
            usage_input_tokens=rsp.usage.input_tokens,
            usage_output_tokens=rsp.usage.output_tokens,
        )

    @staticmethod
    def _to_sdk_message(m: Message) -> dict[str, Any]:
        if m.role == "tool":
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": r.call_id,
                        "content": r.content,
                    }
                    for r in m.tool_results
                ],
            }
        if m.role == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            for tc in m.tool_calls:
                blocks.append(
                    {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments}
                )
            return {"role": "assistant", "content": blocks}
        return {"role": "user", "content": m.content}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_llm_anthropic.py -v`
Expected: 2 pass.

- [ ] **Step 5: Commit**

```bash
git add mobsf_harness/llm/anthropic_client.py tests/unit/test_llm_anthropic.py
git commit -m "feat: Anthropic LLM client"
```

---

## Task 10: OpenAI-Compatible LLM Client

**Files:**
- Modify: `mobsf_harness/llm/openai_client.py` (replace stub)
- Create: `tests/unit/test_llm_openai.py`

OpenAI SDK uses `client.chat.completions.create(...)` with tools in the form `[{"type":"function","function":{"name","description","parameters"}}]`. Response has `choices[0].message.content` and `choices[0].message.tool_calls`, each with an `id`, `function.name`, and `function.arguments` (JSON string).

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_llm_openai.py
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
    # system lives in messages, role=system, as the first message
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_llm_openai.py -v`
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Replace `mobsf_harness/llm/openai_client.py`**

```python
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
            # Return the first (and typical only) tool_result as a single 'tool' message.
            # Multiple results require multiple messages; handled below if len>1.
            if len(m.tool_results) == 1:
                r = m.tool_results[0]
                return {"role": "tool", "tool_call_id": r.call_id, "content": r.content}
            # multiple: the OpenAI schema requires one message per tool result; callers
            # building Message(role="tool") for multi-call turns must send one per result.
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_llm_openai.py -v`
Expected: 2 pass.

- [ ] **Step 5: Commit**

```bash
git add mobsf_harness/llm/openai_client.py tests/unit/test_llm_openai.py
git commit -m "feat: OpenAI-compatible LLM client (OpenRouter, local)"
```

---

## Task 11: Tool Registry + Report Tools

**Files:**
- Create: `mobsf_harness/tools/__init__.py`
- Create: `mobsf_harness/tools/types.py`
- Create: `mobsf_harness/tools/report.py`
- Create: `tests/unit/test_tools_report.py`

- [ ] **Step 1: Write `mobsf_harness/tools/types.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from mobsf_harness.llm.types import ToolSchema


@dataclass
class Tool:
    schema: ToolSchema
    handler: Callable[[dict[str, Any], "ToolContext"], str]
    terminal: bool = False      # True for write_summary / notify


@dataclass
class ToolContext:
    """Passed to every tool handler so the tool can reach state / config / fs."""
    scan_id: int
    app_id: int
    report_json: dict[str, Any]
    report_dir: Any            # Path - avoid import cycle here
    state: Any                 # StateStore
    notify_queue: list         # list[dict] — populated by emit tools
    summary_path: Any          # Path
```

- [ ] **Step 2: Write failing tests**

```python
# tests/unit/test_tools_report.py
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
```

- [ ] **Step 3: Run tests to verify failure**

Run: `pytest tests/unit/test_tools_report.py -v`
Expected: FAIL — module not found.

- [ ] **Step 4: Write `mobsf_harness/tools/report.py`**

```python
from __future__ import annotations

import json
from typing import Any

from mobsf_harness.llm.types import ToolSchema

from .types import Tool, ToolContext


_KNOWN_SECTIONS = {
    "manifest": "manifest_analysis",
    "permissions": "permissions",
    "code_analysis": "code_analysis",
    "network": "network_security",
    "secrets": "secrets",
    "severity": "severity",
}


class GetReportSection:
    def __init__(self) -> None:
        self._schema = ToolSchema(
            name="get_report_section",
            description=(
                "Fetch a named slice of the current MOBSF report JSON. "
                f"Valid names: {sorted(_KNOWN_SECTIONS)}."
            ),
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        )

    @property
    def schema(self) -> ToolSchema: return self._schema
    terminal = False

    def handler(self, args: dict[str, Any], ctx: ToolContext) -> str:
        name = args.get("name", "")
        key = _KNOWN_SECTIONS.get(name)
        if not key:
            return json.dumps({"error": f"unknown section '{name}'", "valid": sorted(_KNOWN_SECTIONS)})
        return json.dumps(ctx.report_json.get(key, {}))


class GetPriorFindingHistory:
    def __init__(self) -> None:
        self._schema = ToolSchema(
            name="get_prior_finding_history",
            description=(
                "Return past occurrences of a finding in prior scans of this app. "
                "Use this to decide whether a finding is new or recurring."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "finding_key": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["finding_key"],
            },
        )

    @property
    def schema(self) -> ToolSchema: return self._schema
    terminal = False

    def handler(self, args: dict[str, Any], ctx: ToolContext) -> str:
        finding_key = args["finding_key"]
        limit = int(args.get("limit", 5))
        history = ctx.state.prior_finding_history(
            ctx.app_id, finding_key, before_scan_id=ctx.scan_id, limit=limit
        )
        return json.dumps(
            {
                "count": len(history),
                "history": [
                    {"severity": f.severity, "title": f.title, "scan_id": f.scan_id}
                    for f in history
                ],
            }
        )
```

- [ ] **Step 5: Write `mobsf_harness/tools/__init__.py`**

```python
from __future__ import annotations

from .emit import Notify, WriteSummary
from .report import GetPriorFindingHistory, GetReportSection
from .types import Tool, ToolContext


def _wrap(instance) -> Tool:
    return Tool(
        schema=instance.schema,
        handler=instance.handler,
        terminal=getattr(instance, "terminal", False),
    )


def build_tool_registry() -> list[Tool]:
    return [
        _wrap(GetReportSection()),
        _wrap(GetPriorFindingHistory()),
        _wrap(WriteSummary()),
        _wrap(Notify()),
        # web_search added later by agent.py using the configured backend
    ]


__all__ = ["build_tool_registry", "Tool", "ToolContext"]
```

Stub emit so imports work (task 13 implements):

```python
# mobsf_harness/tools/emit.py  (stub)
from .types import ToolContext
from mobsf_harness.llm.types import ToolSchema

class WriteSummary:
    schema = ToolSchema(name="write_summary", description="stub", parameters={"type":"object"})
    terminal = True
    def handler(self, args, ctx): raise NotImplementedError

class Notify:
    schema = ToolSchema(name="notify", description="stub", parameters={"type":"object"})
    terminal = True
    def handler(self, args, ctx): raise NotImplementedError
```

- [ ] **Step 6: Run tests to verify pass**

Run: `pytest tests/unit/test_tools_report.py -v`
Expected: 3 pass.

- [ ] **Step 7: Commit**

```bash
git add mobsf_harness/tools/ tests/unit/test_tools_report.py
git commit -m "feat: tool registry + report tools"
```

---

## Task 12: Web Search Tool (pluggable)

**Files:**
- Create: `mobsf_harness/tools/search/__init__.py`
- Create: `mobsf_harness/tools/search/tavily.py`
- Create: `mobsf_harness/tools/search/brave.py`
- Create: `mobsf_harness/tools/search/duckduckgo.py`
- Create: `tests/unit/test_tools_search.py`

Each backend exposes the same `WebSearch` protocol: `search(query: str, limit: int = 5) -> list[dict]`. Factory picks by config.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_tools_search.py
import httpx
import pytest
import respx

from mobsf_harness.config import WebSearchConfig
from mobsf_harness.tools.search import make_web_search
from mobsf_harness.tools.search.tavily import TavilySearch
from mobsf_harness.tools.search.brave import BraveSearch


@respx.mock
def test_tavily_returns_results():
    respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"title": "T", "url": "u", "content": "snippet"}]},
        )
    )
    hits = TavilySearch(api_key="k").search("cve-2024", limit=3)
    assert hits == [{"title": "T", "url": "u", "snippet": "snippet"}]


@respx.mock
def test_brave_returns_results():
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(
            200,
            json={"web": {"results": [{"title": "T2", "url": "u2", "description": "d"}]}},
        )
    )
    hits = BraveSearch(api_key="k").search("cve-2024", limit=3)
    assert hits == [{"title": "T2", "url": "u2", "snippet": "d"}]


def test_factory_picks_duckduckgo_without_api_key():
    cfg = WebSearchConfig(backend="duckduckgo")
    impl = make_web_search(cfg)
    assert type(impl).__name__ == "DuckDuckGoSearch"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_tools_search.py -v`
Expected: FAIL — modules missing.

- [ ] **Step 3: Write `mobsf_harness/tools/search/tavily.py`**

```python
from __future__ import annotations

import httpx


class TavilySearch:
    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def search(self, query: str, limit: int = 5) -> list[dict]:
        rsp = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": self._key,
                "query": query,
                "max_results": limit,
                "include_answer": False,
            },
            timeout=15.0,
        )
        rsp.raise_for_status()
        data = rsp.json()
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
            for r in data.get("results", [])
        ]
```

- [ ] **Step 4: Write `mobsf_harness/tools/search/brave.py`**

```python
from __future__ import annotations

import httpx


class BraveSearch:
    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def search(self, query: str, limit: int = 5) -> list[dict]:
        rsp = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": str(limit)},
            headers={"X-Subscription-Token": self._key, "Accept": "application/json"},
            timeout=15.0,
        )
        rsp.raise_for_status()
        data = rsp.json()
        hits = (data.get("web", {}) or {}).get("results", [])
        return [
            {"title": h.get("title", ""), "url": h.get("url", ""), "snippet": h.get("description", "")}
            for h in hits
        ]
```

- [ ] **Step 5: Write `mobsf_harness/tools/search/duckduckgo.py`**

```python
from __future__ import annotations

# duckduckgo-search is not in our deps to keep the dependency surface small.
# Instead, use DuckDuckGo's HTML endpoint with a fixed, polite rate.
# If users want higher volume, configure tavily or brave.

import re
from html import unescape

import httpx


_RESULT_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
    re.DOTALL,
)


def _strip_tags(s: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", s)).strip()


class DuckDuckGoSearch:
    def __init__(self) -> None:
        pass

    def search(self, query: str, limit: int = 5) -> list[dict]:
        rsp = httpx.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            timeout=15.0,
            headers={"User-Agent": "mobsf-harness/0.1 (+https://example.invalid)"},
        )
        rsp.raise_for_status()
        hits: list[dict] = []
        for m in _RESULT_RE.finditer(rsp.text):
            hits.append(
                {
                    "url": m.group(1),
                    "title": _strip_tags(m.group(2)),
                    "snippet": _strip_tags(m.group(3)),
                }
            )
            if len(hits) >= limit:
                break
        return hits
```

- [ ] **Step 6: Write `mobsf_harness/tools/search/__init__.py`**

```python
from __future__ import annotations

import json
from typing import Any, Protocol

from mobsf_harness.config import WebSearchConfig
from mobsf_harness.llm.types import ToolSchema
from mobsf_harness.tools.types import Tool, ToolContext

from .brave import BraveSearch
from .duckduckgo import DuckDuckGoSearch
from .tavily import TavilySearch


class WebSearch(Protocol):
    def search(self, query: str, limit: int = 5) -> list[dict]: ...


def make_web_search(cfg: WebSearchConfig) -> WebSearch:
    if cfg.backend == "tavily":
        return TavilySearch(api_key=cfg.api_key)
    if cfg.backend == "brave":
        return BraveSearch(api_key=cfg.api_key)
    if cfg.backend == "duckduckgo":
        return DuckDuckGoSearch()
    raise ValueError(f"unknown web_search backend: {cfg.backend}")


class WebSearchTool:
    """Adapter that exposes a WebSearch impl as an agent Tool."""
    def __init__(self, impl: WebSearch) -> None:
        self._impl = impl
        self._schema = ToolSchema(
            name="web_search",
            description=(
                "Search the web for CVE details, library advisories, or vendor docs. "
                "Use sparingly — prefer the report for facts about the app itself."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        )

    @property
    def schema(self) -> ToolSchema: return self._schema
    terminal = False

    def handler(self, args: dict[str, Any], ctx: ToolContext) -> str:
        try:
            hits = self._impl.search(args["query"], int(args.get("limit", 5)))
            return json.dumps({"results": hits})
        except Exception as e:
            return json.dumps({"error": str(e)})


def web_search_tool(cfg: WebSearchConfig) -> Tool:
    impl = make_web_search(cfg)
    inst = WebSearchTool(impl)
    return Tool(schema=inst.schema, handler=inst.handler, terminal=False)
```

- [ ] **Step 7: Run tests to verify pass**

Run: `pytest tests/unit/test_tools_search.py -v`
Expected: 3 pass.

- [ ] **Step 8: Commit**

```bash
git add mobsf_harness/tools/search/ tests/unit/test_tools_search.py
git commit -m "feat: pluggable web search (tavily/brave/duckduckgo)"
```

---

## Task 13: Emit Tools (write_summary, notify)

**Files:**
- Modify: `mobsf_harness/tools/emit.py` (replace stub)
- Create: `tests/unit/test_tools_emit.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_tools_emit.py
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
    # Second call overwrites — we count it in loop contract, not here
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_tools_emit.py -v`
Expected: FAIL — stubs raise.

- [ ] **Step 3: Replace `mobsf_harness/tools/emit.py`**

```python
from __future__ import annotations

import json
from typing import Any

from mobsf_harness.llm.types import ToolSchema

from .types import ToolContext


_VALID_CHANNELS = {"log", "email", "webhook", "any"}
_VALID_SEVERITIES = {"info", "low", "medium", "high", "critical"}


class WriteSummary:
    terminal = True

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="write_summary",
            description=(
                "Record the executive summary for this scan as markdown. "
                "Must be called exactly once. After calling, the loop should end."
            ),
            parameters={
                "type": "object",
                "properties": {"markdown": {"type": "string"}},
                "required": ["markdown"],
            },
        )

    def handler(self, args: dict[str, Any], ctx: ToolContext) -> str:
        md = args.get("markdown", "").strip()
        if not md:
            return json.dumps({"error": "markdown must be non-empty"})
        ctx.summary_path.parent.mkdir(parents=True, exist_ok=True)
        ctx.summary_path.write_text(md)
        return json.dumps({"ok": True, "bytes": len(md)})


class Notify:
    terminal = True

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="notify",
            description=(
                "Emit a notification the operator should see. Use sparingly — "
                "prefer signal over noise. Channel 'any' means route to every "
                "channel enabled in config; specific channels ('log', 'email', "
                "'webhook') constrain routing."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "enum": ["log", "email", "webhook", "any"]},
                    "severity": {"type": "string", "enum": sorted(_VALID_SEVERITIES)},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["channel", "severity", "title", "body"],
            },
        )

    def handler(self, args: dict[str, Any], ctx: ToolContext) -> str:
        channel = args.get("channel", "")
        severity = args.get("severity", "")
        title = args.get("title", "").strip()
        body = args.get("body", "").strip()
        if channel not in _VALID_CHANNELS:
            return json.dumps({"error": f"invalid channel {channel!r}"})
        if severity not in _VALID_SEVERITIES:
            return json.dumps({"error": f"invalid severity {severity!r}"})
        if not title or not body:
            return json.dumps({"error": "title and body required"})
        composed = f"{title}\n\n{body}"
        ctx.notify_queue.append(
            {"channel": channel, "severity": severity, "title": title, "body": body}
        )
        ctx.state.record_notification(ctx.scan_id, channel, severity, composed)
        return json.dumps({"ok": True})
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_tools_emit.py -v`
Expected: 4 pass.

- [ ] **Step 5: Commit**

```bash
git add mobsf_harness/tools/emit.py tests/unit/test_tools_emit.py
git commit -m "feat: emit tools (write_summary, notify)"
```

---

## Task 14: Agent Loop

**Files:**
- Create: `mobsf_harness/agent.py`
- Create: `tests/fixtures/llm_transcripts/happy_path.json`
- Create: `tests/fixtures/llm_transcripts/missing_summary.json`
- Create: `tests/unit/test_agent.py`

The agent loop invokes the LLM, dispatches tool calls, feeds results back, and stops when `write_summary` has been called and no further tool calls arrive — or when a bound is hit.

- [ ] **Step 1: Write `tests/fixtures/llm_transcripts/happy_path.json`**

```json
[
  {
    "text": "I'll review this scan.",
    "tool_calls": [
      {"id": "c1", "name": "get_report_section", "arguments": {"name": "severity"}}
    ],
    "stop_reason": "tool_use"
  },
  {
    "text": "",
    "tool_calls": [
      {"id": "c2", "name": "write_summary", "arguments": {"markdown": "# Summary\n\nAll clear."}}
    ],
    "stop_reason": "tool_use"
  },
  {
    "text": "Done.",
    "tool_calls": [],
    "stop_reason": "end_turn"
  }
]
```

- [ ] **Step 2: Write `tests/fixtures/llm_transcripts/missing_summary.json`**

```json
[
  {
    "text": "I keep thinking...",
    "tool_calls": [
      {"id": "c1", "name": "get_report_section", "arguments": {"name": "permissions"}}
    ],
    "stop_reason": "tool_use"
  },
  {
    "text": "Still thinking...",
    "tool_calls": [],
    "stop_reason": "end_turn"
  }
]
```

- [ ] **Step 3: Write failing tests**

```python
# tests/unit/test_agent.py
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
    # failsafe notification should be recorded on 'log' channel
    notifs = state.notifications_for_scan(scan.id)
    assert any(n.channel == "log" for n in notifs)


def test_max_turns_enforced(
    tmp_path: Path, state: StateStore, report: dict
):
    # LLM that never calls write_summary and always calls a non-terminal tool
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
```

- [ ] **Step 4: Run tests to verify failure**

Run: `pytest tests/unit/test_agent.py -v`
Expected: FAIL — `mobsf_harness.agent` not found.

- [ ] **Step 5: Write `mobsf_harness/agent.py`**

```python
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
            # model has nothing more to do
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

        # dispatch each tool call and append the aggregate tool-role message
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
        messages.append(Message(role="tool", tool_results=results))

    # max_turns reached
    err = f"max_turns reached ({max_turns})"
    _failsafe_notify(state, scan_id, err)
    return AgentOutcome(
        success=False, turns=max_turns, error=err,
        total_input_tokens=total_in, total_output_tokens=total_out,
    )
```

- [ ] **Step 6: Run tests to verify pass**

Run: `pytest tests/unit/test_agent.py -v`
Expected: 3 pass.

- [ ] **Step 7: Commit**

```bash
git add mobsf_harness/agent.py tests/fixtures/llm_transcripts/ tests/unit/test_agent.py
git commit -m "feat: bounded agent tool-use loop"
```

---

## Task 15: Notifier (log / email / webhook)

**Files:**
- Create: `mobsf_harness/notifier.py`
- Create: `tests/unit/test_notifier.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_notifier.py
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from mobsf_harness.config import EmailChannel, LogChannel, NotificationsConfig, WebhookChannel
from mobsf_harness.notifier import Notifier


@pytest.fixture
def log_only(tmp_path: Path) -> tuple[Notifier, Path]:
    path = tmp_path / "n.jsonl"
    cfg = NotificationsConfig(log=LogChannel(path=str(path)))
    return Notifier(cfg), path


def test_log_channel_appends_jsonl(log_only):
    notifier, path = log_only
    notifier.send({"channel": "log", "severity": "high", "title": "t", "body": "b"})
    lines = path.read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["title"] == "t"
    notifier.send({"channel": "log", "severity": "low", "title": "t2", "body": "b2"})
    assert len(path.read_text().splitlines()) == 2


@respx.mock
def test_webhook_channel_posts(tmp_path):
    respx.post("https://hook.test/h").mock(return_value=httpx.Response(200))
    cfg = NotificationsConfig(
        log=LogChannel(path=str(tmp_path / "n.jsonl")),
        webhook=WebhookChannel(url="https://hook.test/h"),
    )
    notifier = Notifier(cfg)
    notifier.send({"channel": "webhook", "severity": "high", "title": "t", "body": "b"})
    assert respx.calls.call_count == 1


@patch("mobsf_harness.notifier.smtplib.SMTP")
def test_email_channel_sends(MockSMTP, tmp_path):
    conn = MagicMock()
    MockSMTP.return_value.__enter__.return_value = conn
    cfg = NotificationsConfig(
        log=LogChannel(path=str(tmp_path / "n.jsonl")),
        email=EmailChannel(
            smtp_host="smtp.test", smtp_port=587,
            from_addr="a@t", to_addrs=["b@t"],
            username="u", password="p",
        ),
    )
    notifier = Notifier(cfg)
    notifier.send({"channel": "email", "severity": "high", "title": "Subj", "body": "Body"})
    assert conn.send_message.called


def test_any_fans_out_to_all_enabled(tmp_path):
    with respx.mock:
        respx.post("https://hook.test/h").mock(return_value=httpx.Response(200))
        cfg = NotificationsConfig(
            log=LogChannel(path=str(tmp_path / "n.jsonl")),
            webhook=WebhookChannel(url="https://hook.test/h"),
        )
        notifier = Notifier(cfg)
        notifier.send({"channel": "any", "severity": "high", "title": "t", "body": "b"})
        # log + webhook (no email configured)
        assert (tmp_path / "n.jsonl").exists()
        assert respx.calls.call_count == 1


def test_disabled_channel_raises_descriptive_error(tmp_path):
    cfg = NotificationsConfig(log=LogChannel(path=str(tmp_path / "n.jsonl")))
    notifier = Notifier(cfg)
    with pytest.raises(ValueError, match="webhook.*not configured"):
        notifier.send({"channel": "webhook", "severity": "high", "title": "t", "body": "b"})
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_notifier.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `mobsf_harness/notifier.py`**

```python
from __future__ import annotations

import json
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import httpx

from mobsf_harness.config import EmailChannel, LogChannel, NotificationsConfig, WebhookChannel


class Notifier:
    def __init__(self, cfg: NotificationsConfig) -> None:
        self._cfg = cfg

    def send(self, intent: dict) -> None:
        channel = intent["channel"]
        if channel == "any":
            self._send_any(intent)
            return
        if channel == "log":
            self._send_log(intent)
            return
        if channel == "webhook":
            self._send_webhook(intent)
            return
        if channel == "email":
            self._send_email(intent)
            return
        raise ValueError(f"unknown channel: {channel}")

    def _send_any(self, intent: dict) -> None:
        if self._cfg.log:
            self._send_log(intent)
        if self._cfg.webhook:
            self._send_webhook(intent)
        if self._cfg.email:
            self._send_email(intent)

    def _send_log(self, intent: dict) -> None:
        if not self._cfg.log:
            raise ValueError("log channel not configured")
        path = Path(self._cfg.log.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {**intent, "ts": datetime.now(timezone.utc).isoformat()}
        with path.open("a") as fp:
            fp.write(json.dumps(record) + "\n")

    def _send_webhook(self, intent: dict) -> None:
        if not self._cfg.webhook:
            raise ValueError("webhook channel not configured")
        wh: WebhookChannel = self._cfg.webhook
        rsp = httpx.post(wh.url, json=intent, headers=wh.headers or {}, timeout=10.0)
        rsp.raise_for_status()

    def _send_email(self, intent: dict) -> None:
        if not self._cfg.email:
            raise ValueError("email channel not configured")
        cfg: EmailChannel = self._cfg.email
        msg = EmailMessage()
        msg["Subject"] = f"[MOBSF {intent['severity']}] {intent['title']}"
        msg["From"] = cfg.from_addr
        msg["To"] = ", ".join(cfg.to_addrs)
        msg.set_content(intent["body"])
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port) as s:
            if cfg.username and cfg.password:
                s.starttls()
                s.login(cfg.username, cfg.password)
            s.send_message(msg)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_notifier.py -v`
Expected: 5 pass.

- [ ] **Step 5: Commit**

```bash
git add mobsf_harness/notifier.py tests/unit/test_notifier.py
git commit -m "feat: notifier with log/email/webhook channels"
```

---

## Task 16: Pipeline Orchestrator

**Files:**
- Create: `mobsf_harness/pipeline.py`
- Create: `tests/integration/test_pipeline.py`

The pipeline runs a single app through: version check → skip-if-unchanged → fetch → MOBSF upload → MOBSF scan trigger → MOBSF poll → fetch report (JSON + PDF) → load prior scan → run agent → route notifications → write finding rows from raw report. Each stage writes status to `scans` before moving on.

- [ ] **Step 1: Write failing integration test**

```python
# tests/integration/test_pipeline.py
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


def test_new_app_is_scanned_and_summarized(tmp_path: Path, fixtures_dir: Path):
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


def test_unchanged_version_skipped(tmp_path: Path, fixtures_dir: Path):
    report = json.loads((fixtures_dir / "mobsf" / "small_report.json").read_text())
    state = StateStore(tmp_path / "state.sqlite"); state.initialize()
    # Seed: already-completed scan at version 100
    app = state.get_or_create_app("android", "com.e", "play_store")
    prior = state.create_scan(app.id, "1.0.0", "100", "h", "reports/x")
    state.update_scan_status(prior.id, "done")

    deps = PipelineDeps(
        state=state,
        mobsf_client=_fake_mobsf(report),
        fetcher_factory=lambda app: _fake_fetcher(),
        llm_client=FakeLlmClient([]),  # never invoked
        reports_root=tmp_path / "reports",
    )
    cfg = _cfg(tmp_path)

    result = run_for_app(deps, cfg, cfg.apps[0])

    assert result.status == "skipped"
    assert result.reason == "unchanged_version"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/integration/test_pipeline.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `mobsf_harness/pipeline.py`**

```python
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from mobsf_harness.agent import run_agent
from mobsf_harness.config import AppEntry, Config
from mobsf_harness.fetchers.base import Fetcher
from mobsf_harness.llm.types import LlmClient
from mobsf_harness.mobsf_client import MobsfClient
from mobsf_harness.notifier import Notifier
from mobsf_harness.state import StateStore
from mobsf_harness.tools import build_tool_registry
from mobsf_harness.tools.search import web_search_tool


log = logging.getLogger("mobsf_harness.pipeline")


@dataclass
class PipelineResult:
    status: str       # "done" | "skipped" | "failed"
    reason: str = ""
    scan_id: int | None = None


@dataclass
class PipelineDeps:
    state: StateStore
    mobsf_client: Any              # MobsfClient or duck
    fetcher_factory: Callable[[AppEntry], Fetcher]
    llm_client: LlmClient
    reports_root: Path
    notifier: Notifier | None = None


SEVERITY_KEYS = {"high", "medium", "low", "info", "critical"}


def _flatten_findings(report: dict[str, Any]) -> list[tuple[str, str, str, dict]]:
    """Extract (finding_key, severity, title, raw) tuples from a MOBSF report."""
    out: list[tuple[str, str, str, dict]] = []
    code = report.get("code_analysis", {}).get("findings", {})
    if isinstance(code, dict):
        for key, raw in code.items():
            sev = raw.get("metadata", {}).get("severity", "info") if isinstance(raw, dict) else "info"
            out.append((f"code:{key}", sev, key, raw if isinstance(raw, dict) else {"raw": raw}))
    net = report.get("network_security", {}).get("network_findings", [])
    if isinstance(net, list):
        for i, raw in enumerate(net):
            sev = raw.get("severity", "info") if isinstance(raw, dict) else "info"
            out.append((f"net:{i}:{raw.get('rule','')}", sev, str(raw.get("description", ""))[:120], raw if isinstance(raw, dict) else {}))
    manifest = report.get("manifest_analysis", {}).get("manifest_findings", [])
    if isinstance(manifest, list):
        for i, raw in enumerate(manifest):
            sev = raw.get("severity", "info") if isinstance(raw, dict) else "info"
            out.append((f"manifest:{i}:{raw.get('rule','')}", sev, str(raw.get("title", ""))[:120], raw if isinstance(raw, dict) else {}))
    for sec in report.get("secrets", []) or []:
        if isinstance(sec, str):
            out.append((f"secret:{sec[:40]}", "high", f"secret: {sec[:60]}", {"secret": sec}))
    return out


_SEVERITY_ORDER = ["info", "low", "medium", "high", "critical"]


def _severity_rank(sev: str) -> int:
    try:
        return _SEVERITY_ORDER.index(sev)
    except ValueError:
        return 0


def _build_digest(report: dict[str, Any], limit: int = 20) -> dict:
    sev = report.get("severity", {})
    findings = _flatten_findings(report)
    top = sorted(findings, key=lambda f: _severity_rank(f[1]), reverse=True)[:limit]
    return {
        "severity_counts": sev,
        "top_findings": [{"key": k, "severity": s, "title": t} for k, s, t, _ in top],
        "app_name": report.get("app_name"),
    }


def _prior_summary(state: StateStore, app_id: int, prior_scan_id: int | None) -> dict:
    if prior_scan_id is None:
        return {"present": False}
    findings = state.findings_for_scan(prior_scan_id)
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return {
        "present": True,
        "severity_counts": counts,
        "finding_keys": [f.finding_key for f in findings][:40],
    }


def run_for_app(
    deps: PipelineDeps,
    cfg: Config,
    app: AppEntry,
    *,
    force_rescan: bool = False,
) -> PipelineResult:
    state = deps.state
    app_rec = state.get_or_create_app(app.platform, app.identifier, app.source)
    state.touch_app(app_rec.id)
    fetcher = deps.fetcher_factory(app)

    try:
        info = fetcher.latest_version(app)
    except Exception as e:
        log.exception("latest_version failed")
        return PipelineResult(status="failed", reason=f"latest_version: {e}")

    # skip if unchanged (unless forced)
    prior = state.latest_completed_scan(app_rec.id)
    if prior and prior.version_code == info.version_code and not force_rescan:
        return PipelineResult(status="skipped", reason="unchanged_version")

    report_dir = deps.reports_root / app.platform / app.identifier / f"{info.version_name}-{info.version_code}"
    report_dir.mkdir(parents=True, exist_ok=True)

    scan_rec = None
    try:
        fetch = fetcher.fetch(app, version_code=info.version_code, dest_dir=report_dir)
        scan_rec = state.create_scan(
            app_id=app_rec.id,
            version_name=fetch.version_name,
            version_code=fetch.version_code,
            sha256=fetch.sha256,
            report_dir=str(report_dir),
        )
        state.update_scan_status(scan_rec.id, "downloading")
        (report_dir / "artifact.sha256").write_text(fetch.sha256)

        state.update_scan_status(scan_rec.id, "scanning")
        mobsf_hash = deps.mobsf_client.upload(fetch.artifact_path)
        deps.mobsf_client.scan(mobsf_hash)
        state.update_scan_status(scan_rec.id, "scanning", mobsf_scan_hash=mobsf_hash)
        report_json = deps.mobsf_client.report_json(mobsf_hash)
        (report_dir / "mobsf.json").write_text(json.dumps(report_json))
        try:
            deps.mobsf_client.download_pdf(mobsf_hash, report_dir / "mobsf.pdf")
        except Exception:
            log.warning("PDF download failed; continuing")

        # persist findings (for prior_finding_history lookups on next runs)
        for key, sev, title, raw in _flatten_findings(report_json):
            state.add_finding(scan_rec.id, key, sev, title, raw)

        state.update_scan_status(scan_rec.id, "analyzing")

        # run agent
        tools = build_tool_registry() + [web_search_tool(cfg.web_search)]
        prior_id = prior.id if prior else None
        user_prompt = json.dumps(
            {
                "app": {
                    "platform": app.platform,
                    "identifier": app.identifier,
                    "version_name": fetch.version_name,
                    "version_code": fetch.version_code,
                },
                "current_digest": _build_digest(report_json),
                "prior": _prior_summary(state, app_rec.id, prior_id),
                "policy": cfg.policy,
            },
            indent=2,
        )

        outcome = run_agent(
            llm_client=deps.llm_client,
            model=cfg.llm.model,
            max_turns=cfg.llm.max_turns,
            max_tokens_per_session=cfg.llm.max_tokens_per_session,
            tools=tools,
            report_json=report_json,
            report_dir=report_dir,
            summary_path=report_dir / "summary.md",
            state=state,
            scan_id=scan_rec.id,
            app_id=app_rec.id,
            system=(
                "You are a mobile application security analyst. Review the MOBSF "
                "scan provided and produce an executive summary and any operator "
                "notifications that follow the provided policy. Prefer signal "
                "over noise. You MUST call write_summary exactly once before "
                "ending the session."
            ),
            user_prompt=user_prompt,
        )

        if outcome.success:
            state.update_scan_status(scan_rec.id, "done", finished_at=datetime.now(timezone.utc))
            # route notifications
            if deps.notifier:
                for intent in _pending_notifications(state, scan_rec.id):
                    try:
                        deps.notifier.send(intent)
                        state.mark_notification_sent(intent["_id"])
                    except Exception as e:
                        state.mark_notification_failed(intent["_id"], str(e))
            return PipelineResult(status="done", scan_id=scan_rec.id)
        else:
            state.update_scan_status(
                scan_rec.id, "failed",
                finished_at=datetime.now(timezone.utc),
                error_message=outcome.error,
            )
            return PipelineResult(status="failed", reason=outcome.error, scan_id=scan_rec.id)

    except Exception as e:
        log.exception("pipeline failed")
        if scan_rec:
            state.update_scan_status(
                scan_rec.id, "failed",
                finished_at=datetime.now(timezone.utc),
                error_message=str(e),
            )
            return PipelineResult(status="failed", reason=str(e), scan_id=scan_rec.id)
        return PipelineResult(status="failed", reason=str(e))


def _pending_notifications(state: StateStore, scan_id: int) -> list[dict]:
    """Translate DB rows into the dict format Notifier.send expects."""
    out: list[dict] = []
    for n in state.notifications_for_scan(scan_id):
        if n.sent_at is not None:
            continue
        title, _, body = n.body.partition("\n\n")
        out.append({
            "_id": n.id,
            "channel": n.channel,
            "severity": n.severity,
            "title": title,
            "body": body,
        })
    return out
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/integration/test_pipeline.py -v`
Expected: 2 pass.

- [ ] **Step 5: Commit**

```bash
git add mobsf_harness/pipeline.py tests/integration/test_pipeline.py
git commit -m "feat: pipeline orchestrator"
```

---

## Task 17: CLI

**Files:**
- Create: `mobsf_harness/cli.py`
- Create: `tests/unit/test_cli.py` (smoke only)

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_cli.py
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_cli.py -v`
Expected: FAIL — `mobsf_harness.cli` missing.

- [ ] **Step 3: Write `mobsf_harness/cli.py`**

```python
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from mobsf_harness.agent import run_agent
from mobsf_harness.config import load_config
from mobsf_harness.fetchers import fetcher_for
from mobsf_harness.llm import make_client
from mobsf_harness.mobsf_client import MobsfClient
from mobsf_harness.notifier import Notifier
from mobsf_harness.pipeline import PipelineDeps, run_for_app
from mobsf_harness.state import StateStore
from mobsf_harness.tools import build_tool_registry
from mobsf_harness.tools.search import web_search_tool


DEFAULT_CONFIG = Path("apps.yaml")
DEFAULT_STATE = Path("state.sqlite")
DEFAULT_REPORTS = Path("reports")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler("harness.log"), logging.StreamHandler(sys.stderr)],
    )


def _build_deps(cfg) -> PipelineDeps:
    state = StateStore(DEFAULT_STATE); state.initialize()
    return PipelineDeps(
        state=state,
        mobsf_client=MobsfClient(cfg.mobsf.url, cfg.mobsf.api_key),
        fetcher_factory=fetcher_for,
        llm_client=make_client(cfg.llm),
        reports_root=DEFAULT_REPORTS,
        notifier=Notifier(cfg.notifications),
    )


@click.group()
def main() -> None:
    _setup_logging()


@main.command()
@click.option("--config", "config_path", type=click.Path(exists=True), default=str(DEFAULT_CONFIG))
@click.option("--only", default=None, help="Only run the app with this identifier")
@click.option("--force-rescan", is_flag=True, default=False)
def run(config_path: str, only: str | None, force_rescan: bool) -> None:
    """Run the harness over all configured apps."""
    cfg = load_config(Path(config_path))
    deps = _build_deps(cfg)
    for app in cfg.apps:
        if only and app.identifier != only:
            continue
        click.echo(f"Running {app.identifier} ...")
        result = run_for_app(deps, cfg, app, force_rescan=force_rescan)
        click.echo(f"  -> {result.status} {result.reason}")


@main.command("list")
@click.option("--config", "config_path", type=click.Path(exists=True), default=str(DEFAULT_CONFIG))
def list_cmd(config_path: str) -> None:
    """List all tracked apps and their latest scan status."""
    cfg = load_config(Path(config_path))
    state = StateStore(DEFAULT_STATE); state.initialize()
    for app in cfg.apps:
        rec = state.get_or_create_app(app.platform, app.identifier, app.source)
        latest = state.latest_completed_scan(rec.id)
        ver = f"{latest.version_name}-{latest.version_code}" if latest else "never scanned"
        click.echo(f"{app.platform:8} {app.identifier:40} {ver}")


@main.command()
@click.argument("identifier")
@click.option("--config", "config_path", type=click.Path(exists=True), default=str(DEFAULT_CONFIG))
def status(identifier: str, config_path: str) -> None:
    """Print scan history for one app."""
    cfg = load_config(Path(config_path))
    state = StateStore(DEFAULT_STATE); state.initialize()
    app = next((a for a in cfg.apps if a.identifier == identifier), None)
    if app is None:
        click.echo(f"{identifier}: not in config", err=True); sys.exit(1)
    rec = state.get_or_create_app(app.platform, app.identifier, app.source)
    import sqlite3
    conn = sqlite3.connect(DEFAULT_STATE); conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM scans WHERE app_id=? ORDER BY id DESC", (rec.id,)
    ).fetchall()
    for r in rows:
        click.echo(f"#{r['id']:4d} {r['status']:10} {r['version_name']}-{r['version_code']} "
                   f"{r['started_at']} {r['error_message'] or ''}")


@main.command()
@click.argument("scan_id", type=int)
@click.option("--config", "config_path", type=click.Path(exists=True), default=str(DEFAULT_CONFIG))
def replay_agent(scan_id: int, config_path: str) -> None:
    """Re-run the agent on an existing scan. Useful after LLM/policy changes."""
    cfg = load_config(Path(config_path))
    state = StateStore(DEFAULT_STATE); state.initialize()
    scan = state.get_scan(scan_id)
    if scan is None or not scan.report_dir:
        click.echo(f"scan {scan_id} not found or has no report_dir", err=True); sys.exit(1)
    report_path = Path(scan.report_dir) / "mobsf.json"
    if not report_path.exists():
        click.echo(f"mobsf.json missing at {report_path}", err=True); sys.exit(1)
    report = json.loads(report_path.read_text())
    tools = build_tool_registry() + [web_search_tool(cfg.web_search)]
    outcome = run_agent(
        llm_client=make_client(cfg.llm),
        model=cfg.llm.model,
        max_turns=cfg.llm.max_turns,
        max_tokens_per_session=cfg.llm.max_tokens_per_session,
        tools=tools,
        report_json=report,
        report_dir=Path(scan.report_dir),
        summary_path=Path(scan.report_dir) / "summary.md",
        state=state,
        scan_id=scan.id,
        app_id=scan.app_id,
        system="Re-triage an existing scan.",
        user_prompt=json.dumps({"report_path": str(report_path), "policy": cfg.policy}),
    )
    click.echo(f"success={outcome.success} turns={outcome.turns} error={outcome.error}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_cli.py -v`
Expected: 2 pass.

- [ ] **Step 5: Commit**

```bash
git add mobsf_harness/cli.py tests/unit/test_cli.py
git commit -m "feat: CLI (run/list/status/replay-agent)"
```

---

## Task 18: README + systemd timer example

**Files:**
- Create: `README.md`
- Create: `deploy/mobsf-harness.service`
- Create: `deploy/mobsf-harness.timer`

- [ ] **Step 1: Create `README.md`**

```markdown
# mobsf-harness

Scheduled, AI-assisted MOBSF analysis for mobile apps.

## Quick start

```bash
pip install -e '.[dev]'
cp apps.example.yaml apps.yaml
# edit apps.yaml; set env vars for api keys
export MOBSF_API_KEY=...
export ANTHROPIC_API_KEY=...
mobsf-harness run
```

## Commands

- `mobsf-harness run [--only <id>] [--force-rescan]`
- `mobsf-harness list`
- `mobsf-harness status <identifier>`
- `mobsf-harness replay-agent <scan_id>`

## Deploying as a timer

See `deploy/mobsf-harness.service` and `deploy/mobsf-harness.timer`.

## LLM providers

`llm.provider` in `apps.yaml`:

- `anthropic` — uses the Anthropic SDK (native). Best fidelity, needs `ANTHROPIC_API_KEY`.
- `openai-compatible` — uses the OpenAI SDK with a configurable `base_url`. Works with OpenRouter (`https://openrouter.ai/api/v1`), local Ollama (`http://localhost:11434/v1`), vLLM, LM Studio, LocalAI.

Tool-use quality varies across models. Opus/Sonnet and strong mid-tier models work well. Small local models (7B–13B) may produce weaker tool calls and triage judgment.
```

- [ ] **Step 2: Create `deploy/mobsf-harness.service`**

```ini
[Unit]
Description=MOBSF Harness scheduled scan
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/mobsf-harness
EnvironmentFile=/etc/mobsf-harness/env
ExecStart=/opt/mobsf-harness/.venv/bin/mobsf-harness run
User=mobsf-harness
```

- [ ] **Step 3: Create `deploy/mobsf-harness.timer`**

```ini
[Unit]
Description=MOBSF Harness daily scan timer

[Timer]
OnCalendar=daily
RandomizedDelaySec=30min
Persistent=true
Unit=mobsf-harness.service

[Install]
WantedBy=timers.target
```

- [ ] **Step 4: Commit**

```bash
git add README.md deploy/
git commit -m "docs: readme and systemd deploy files"
```

---

## Task 19: End-to-end smoke test (opt-in)

**Files:**
- Create: `tests/e2e/__init__.py`
- Create: `tests/e2e/test_smoke.py`
- Create: `tests/fixtures/artifacts/README.md` (instructions, not the APK itself)

The smoke test is gated by `MOBSF_HARNESS_E2E=1`. It assumes a reachable MOBSF and a real LLM key. We don't commit an APK fixture by default (license concerns); instruct the operator to drop one in.

- [ ] **Step 1: Write `tests/e2e/test_smoke.py`**

```python
import os
from pathlib import Path

import pytest

from mobsf_harness.agent import run_agent  # noqa: F401  (ensures import works)
from mobsf_harness.config import load_config
from mobsf_harness.fetchers import fetcher_for
from mobsf_harness.llm import make_client
from mobsf_harness.mobsf_client import MobsfClient
from mobsf_harness.notifier import Notifier
from mobsf_harness.pipeline import PipelineDeps, run_for_app
from mobsf_harness.state import StateStore


pytestmark = pytest.mark.e2e


@pytest.mark.skipif(
    os.environ.get("MOBSF_HARNESS_E2E") != "1",
    reason="set MOBSF_HARNESS_E2E=1 to run end-to-end",
)
def test_full_pipeline_against_real_mobsf_and_llm(tmp_path: Path):
    apps_yaml = Path(__file__).parent.parent / "fixtures" / "artifacts" / "apps.e2e.yaml"
    assert apps_yaml.exists(), "create tests/fixtures/artifacts/apps.e2e.yaml — see README"
    cfg = load_config(apps_yaml)
    state = StateStore(tmp_path / "state.sqlite"); state.initialize()
    deps = PipelineDeps(
        state=state,
        mobsf_client=MobsfClient(cfg.mobsf.url, cfg.mobsf.api_key),
        fetcher_factory=fetcher_for,
        llm_client=make_client(cfg.llm),
        reports_root=tmp_path / "reports",
        notifier=Notifier(cfg.notifications),
    )
    for app in cfg.apps:
        result = run_for_app(deps, cfg, app)
        assert result.status in {"done", "skipped"}, f"{app.identifier}: {result.reason}"
```

- [ ] **Step 2: Create `tests/fixtures/artifacts/README.md`**

```markdown
# E2E fixtures

Drop a small open-source APK or IPA here and create `apps.e2e.yaml` pointing
at it with `source: drop_dir` and a `drop_path` of this directory structured
as `<version>-<code>/artifact.apk`. Then:

```bash
MOBSF_HARNESS_E2E=1 \
MOBSF_API_KEY=... \
ANTHROPIC_API_KEY=... \
pytest -m e2e tests/e2e/
```
```

- [ ] **Step 3: Run to verify it's skipped by default**

Run: `pytest tests/e2e/ -v`
Expected: 1 skipped.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/ tests/fixtures/artifacts/
git commit -m "test: opt-in e2e smoke test"
```

---

## Final Verification

- [ ] **Run the full test suite**

Run: `pytest -v`
Expected: all unit + integration tests pass; e2e skipped.

- [ ] **Run ruff**

Run: `ruff check mobsf_harness/ tests/`
Expected: no errors.

- [ ] **Smoke-invoke the CLI**

Run: `mobsf-harness --help`
Expected: commands `run`, `list`, `status`, `replay-agent` listed.

---

## Spec Coverage Check

| Spec section | Tasks covering it |
|---|---|
| Config schema (apps.yaml) | Task 2 |
| SQLite state | Task 3 |
| MOBSF client | Task 4 |
| Drop-dir fetcher | Task 5 |
| Play Store fetcher | Task 6 |
| App Store fetcher | Task 7 |
| LLM abstraction (Anthropic) | Task 8, 9 |
| LLM abstraction (OpenAI-compatible, covers OpenRouter + local) | Task 8, 10 |
| Pluggable web search (Tavily/Brave/DuckDuckGo) | Task 12 |
| Agent tools (report, history) | Task 11 |
| Agent tools (write_summary, notify) | Task 13 |
| Bounded agent loop + failsafe | Task 14 |
| Notifier (log/email/webhook) | Task 15 |
| Pipeline orchestrator | Task 16 |
| CLI (run/list/status/replay-agent) | Task 17 |
| systemd timer | Task 18 |
| E2E smoke | Task 19 |
