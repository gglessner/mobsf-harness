# MOBSF Agent Harness — Design

**Date:** 2026-04-20
**Status:** Draft — pending user review

## Goal

A Python test harness that performs scheduled, automated security analysis of mobile applications using [MOBSF](https://github.com/MobSF/Mobile-Security-Framework-MobSF). Each scheduled run downloads the latest versions of tracked Android/iOS apps, scans them through MOBSF, and invokes a bounded AI agent loop that produces an executive summary and emits operator-judged notifications.

## Non-goals

- Replacing MOBSF itself or wrapping its UI.
- Managing the MOBSF deployment lifecycle (install, upgrade, health). MOBSF is assumed to be reachable at a configured URL with an API key.
- Real-time / on-push scanning. This is a scheduled harness.
- Multi-tenant or multi-operator use. Single-operator configuration.
- Testing the correctness of `gplaycli`, `ipatool`, MOBSF, or LLM response *quality* itself.

## Decisions locked during brainstorming

| # | Decision | Value |
|---|---|---|
| 1 | AI agent role | Orchestrator of analysis; scripted pipeline handles deterministic I/O |
| 2 | Invocation | Python CLI triggered by cron or systemd timer |
| 3 | App sources | Google Play Store (Android, via `gplaycli`), App Store (iOS, via `ipatool` best-effort, with manual drop-directory fallback) |
| 4 | MOBSF deployment | Pre-installed; URL + API key configurable (local or remote) |
| 5 | Outputs | Raw MOBSF report + AI executive summary + AI-judged notifications |
| 6 | Notification channels | Email (SMTP), webhook (HTTP POST), local log file (JSONL) — any subset configurable |
| 7 | Scheduling & dedup | Fixed schedule; skip if store version unchanged since last scan |
| 8 | Scan types | Static by default; dynamic analysis optional per-app (forwarded to MOBSF if enabled) |
| 9 | Config | `apps.yaml` for user-editable input; `state.sqlite` for harness-managed state |
| 10 | Report layout | `reports/<platform>/<identifier>/<version>/{artifact, mobsf.json, mobsf.pdf, summary.md, scan.log}` |
| 11 | Agent context | Current MOBSF JSON + prior scan digest + pluggable web search |
| 12 | LLM providers | "anthropic" (Anthropic SDK, native) and "openai-compatible" (OpenAI SDK, configurable `base_url` — covers OpenRouter, Ollama, vLLM, LM Studio, LocalAI) |
| 13 | Web search | Pluggable: Tavily, Brave, or DuckDuckGo — selected by config |
| 14 | Architecture | Hybrid: scripted pipeline + bounded per-scan agent loop |

## High-level architecture

```
cron / systemd timer
    └── mobsf-harness run --config apps.yaml
         │
         ▼
  Scripted pipeline (deterministic, per app)
   Version Check → Fetcher → MOBSF Upload+Poll → Report Fetch
                       │                                │
                       │   (skip if version unchanged)  ▼
                       ▼                       Analysis Agent
                  skip / done                  (Claude tool-use loop,
                                                bounded)
                                                      │
                                                      ▼
                                              Notification Router
                                              (email / webhook / log)
         │
         ▼
  Storage: reports/, state.sqlite, apps.yaml
```

**Failure model:** per-app errors are isolated to that app's scan record. Partial success across the apps list is the norm; a bad download or MOBSF hiccup on app X does not stop apps Y, Z.

**External dependencies**

- MOBSF reachable at configurable URL with API key.
- `gplaycli` (or equivalent) for Google Play downloads.
- `ipatool` for App Store — best-effort; falls back to `drops/ios/<bundle_id>/`.
- Anthropic SDK and/or OpenAI SDK (whichever provider is configured).
- Optional: SMTP server (email), outbound HTTPS (webhook), web search provider API key.

## Components

```
mobsf_harness/
├── cli.py              # entry point: `mobsf-harness run|list|status|rescan|replay-agent`
├── config.py           # loads apps.yaml + env (pydantic schema)
├── state.py            # SQLite access: apps, scans, findings, notifications
├── fetchers/
│   ├── __init__.py     # Fetcher interface + factory
│   ├── play_store.py   # gplaycli wrapper (Android)
│   ├── app_store.py    # ipatool wrapper (iOS, best-effort)
│   └── drop_dir.py     # manual-drop fallback
├── mobsf_client.py     # REST client: upload, scan, poll, fetch report
├── llm/
│   ├── __init__.py     # LLMClient interface + factory
│   ├── anthropic.py    # Anthropic SDK impl
│   └── openai_compat.py# OpenAI SDK impl (base_url configurable)
├── tools/              # Tools exposed to the agent
│   ├── __init__.py     # registry + Anthropic/OpenAI schema marshalling
│   ├── report.py       # get_report_section, get_prior_finding_history
│   ├── search/
│   │   ├── __init__.py # WebSearch interface
│   │   ├── tavily.py
│   │   ├── brave.py
│   │   └── duckduckgo.py
│   └── emit.py         # write_summary, notify (terminal actions)
├── agent.py            # analysis loop: build prompt, tool-use loop,
│                       # collect terminal actions, bounded by max_turns
├── notifier.py         # routes notify() calls to configured channels
└── pipeline.py         # orchestrates per-app: version → fetch → scan
                        # → agent → notifier
```

**Boundaries:**

- `pipeline.py` is the deterministic orchestrator. It never calls an LLM directly.
- `agent.py` is the only LLM consumer. It receives a `ScanContext` and returns structured results (summary markdown + list of notification intents).
- Tools are thin: validate args, call underlying lib/SDK, return JSON. No business logic.
- Every module is independently testable with fakes at its boundary.

**Quality caveat on LLM choice.** Tool-use reliability varies across models. Opus/Sonnet produce the best analysis. Mid-tier cloud models (GPT-4-class, DeepSeek, Qwen-cloud) work well. Small local models (7B–13B) often produce weaker JSON tool calls and weaker triage judgment. The harness works with any compatible endpoint, but *the quality of AI-judged notifications is model-dependent* — operator's choice, operator's responsibility.

## Data model

### `apps.yaml` — user-editable input

```yaml
defaults:
  dynamic_analysis: false
  notification_channels: [log]     # subset of: log, email, webhook

mobsf:
  url: http://localhost:8000
  api_key_env: MOBSF_API_KEY

llm:
  provider: anthropic              # or "openai-compatible"
  model: claude-opus-4-7
  base_url: null                   # used only for openai-compatible
  api_key_env: ANTHROPIC_API_KEY
  max_turns: 12
  max_tokens_per_session: 100000

web_search:
  backend: tavily                  # or "brave", "duckduckgo"
  api_key_env: TAVILY_API_KEY      # unused for duckduckgo

notifications:
  log:
    path: ./notifications.jsonl
  email:
    smtp_host: smtp.example.com
    smtp_port: 587
    from_addr: mobsf@example.com
    to_addrs: [sec@example.com]
    username_env: SMTP_USER
    password_env: SMTP_PASS
  webhook:
    url: https://hooks.slack.com/services/...
    # optional: headers, auth config

policy: |
  Notify on any NEW high/critical finding, any new exported activity,
  or any new hardcoded secret. Recurring issues are not news.

apps:
  - platform: android
    package_id: com.example.app
    source: play_store             # or "drop_dir"
    notification_channels: [log, webhook]
    dynamic_analysis: false
    tags: [prod, customer-facing]

  - platform: ios
    bundle_id: com.example.iosapp
    source: drop_dir               # or "app_store"
    drop_path: ./drops/ios/com.example.iosapp/
```

Secrets are always env-referenced, never inline.

### `state.sqlite` — harness-managed

```sql
CREATE TABLE apps (
  id                INTEGER PRIMARY KEY,
  platform          TEXT NOT NULL,              -- 'android' | 'ios'
  identifier        TEXT NOT NULL,              -- package_id / bundle_id
  source            TEXT NOT NULL,              -- 'play_store'|'app_store'|'drop_dir'
  first_seen        TEXT NOT NULL,
  last_checked      TEXT,
  UNIQUE(platform, identifier)
);

CREATE TABLE scans (
  id                INTEGER PRIMARY KEY,
  app_id            INTEGER NOT NULL REFERENCES apps(id),
  version_name      TEXT,
  version_code      TEXT,
  sha256            TEXT NOT NULL,
  started_at        TEXT NOT NULL,
  finished_at       TEXT,
  status            TEXT NOT NULL,
      -- queued|downloading|scanning|analyzing|done|failed
  error_message     TEXT,
  report_dir        TEXT,
  mobsf_scan_hash   TEXT,
  UNIQUE(app_id, sha256)
);

CREATE TABLE findings (
  id                INTEGER PRIMARY KEY,
  scan_id           INTEGER NOT NULL REFERENCES scans(id),
  finding_key       TEXT NOT NULL,
  severity          TEXT NOT NULL,              -- info|low|medium|high|critical
  title             TEXT NOT NULL,
  raw               TEXT NOT NULL               -- JSON blob
);
CREATE INDEX idx_findings_scan ON findings(scan_id);
CREATE INDEX idx_findings_key  ON findings(finding_key);

CREATE TABLE notifications (
  id                INTEGER PRIMARY KEY,
  scan_id           INTEGER NOT NULL REFERENCES scans(id),
  channel           TEXT NOT NULL,
  severity          TEXT NOT NULL,
  body              TEXT NOT NULL,
  sent_at           TEXT,
  error_message     TEXT
);
```

Why `findings` as a separate table: it lets `get_prior_finding_history` answer "has this exact finding been seen in previous scans of this app?" quickly, which is what powers the agent's diff-based judgment.

### Reports on disk

```
reports/
  android/
    com.example.app/
      1.2.3-4501/                  # <version_name>-<version_code>
        artifact.apk
        artifact.sha256
        mobsf.json                 # raw MOBSF report
        mobsf.pdf
        summary.md                 # AI-written
        scan.log                   # pipeline + agent trace (JSONL)
  ios/
    com.example.iosapp/
      2.0.1-2010/
        artifact.ipa
        ...
```

## Agent design

**Scope:** the agent runs *once per completed scan*. It's a bounded tool-use loop (`max_turns`, default 12), not a long-running session.

**Inputs:**

- Scan context: platform, identifier, version, scan date.
- Prior scan summary: version + severity counts + list of `finding_key`s (compact — not full JSON).
- Current MOBSF report attached as a **digest** on turn 1 (severity counts, top 20 findings, manifest summary). Full report is available via `get_report_section`.
- Operator policy (free-text, from `apps.yaml`).

**Tools:**

| Tool | Purpose |
|---|---|
| `get_report_section(name)` | Fetch a named slice of the MOBSF report (`manifest`, `permissions`, `code_analysis`, `network`, `secrets`, etc.) |
| `get_prior_finding_history(finding_key, limit=5)` | Past occurrences of a finding (severity, version, date) across prior scans of this app |
| `web_search(query)` | Pluggable backend. Used for CVE lookups, library advisories |
| `write_summary(markdown)` | **Terminal.** Records executive summary to `summary.md`. Must be called exactly once |
| `notify(channel, severity, title, body)` | **Terminal.** Queues a notification. May be called 0+ times. `channel` is `"log"`, `"email"`, `"webhook"`, or `"any"` |

**Loop contract:**

- Loop ends when `write_summary` has been called *and* the model emits no further tool calls, OR when `max_turns` or `max_tokens_per_session` is hit.
- If `write_summary` is never called: scan is marked `failed` (reason: "agent did not produce summary"), and a notification is sent via the `log` channel regardless of agent instructions (failsafe).
- All tool calls + responses are written to `scan.log` (JSONL) for post-hoc auditing.
- Tool-call errors are returned *to the agent* as tool results (not raised) so the agent can recover.

**Prompt shape (simplified):**

```
SYSTEM:
  You are a mobile application security analyst. You review a completed
  MOBSF scan and produce (a) an executive summary and (b) any notifications
  worth sending to the operator. Use tools to investigate. Be concise.
  Prefer signal over noise — the operator has asked for AI-judged notifications.

USER:
  App: com.example.app (android), version 1.2.3 (code 4501), scanned 2026-04-20.
  Prior scan: 1.2.1 (code 4480), 2026-04-10.
      severity counts: {high: 1, medium: 3, low: 5}
      notable prior finding_keys: [...]
  Current scan digest: {...}
  Operator policy: <free-text from apps.yaml>

  Begin your analysis.
```

**Why this is robust across model tiers:**

- Required terminal tool (`write_summary`) gives a clear stop condition even weak models can hit.
- `notify` is optional — a weak model that can't judge gracefully degrades to "summary only, no notifications" rather than producing junk.
- Bounded turns + token budget prevent runaway loops on buggy tool-use from local models.

## Operations

### Scheduling

Preferred: systemd timer.

```
[Unit]
Description=MOBSF Harness scheduled scan
[Timer]
OnCalendar=daily
RandomizedDelaySec=30min
Persistent=true
[Install]
WantedBy=timers.target
```

A single `mobsf-harness run` iterates all apps serially — MOBSF is the bottleneck and prefers serial uploads. Dozens of apps per run is fine.

### CLI surface

```
mobsf-harness run [--config apps.yaml] [--only <id>] [--force-rescan]
mobsf-harness list
mobsf-harness status <id>
mobsf-harness rescan <id>              # force next run to rescan this app
mobsf-harness replay-agent <scan_id>   # re-run agent on existing scan
```

`replay-agent` lets the operator re-triage old scans without re-downloading or re-scanning when they change LLM provider, model, or policy.

### Idempotency and retries

- Each pipeline stage writes its completion to `scans` before advancing. A crashed run resumes from the last completed stage.
- Fetchers: up to 3 retries with exponential backoff for transient errors; permanent errors (404, region-unavailable) mark the scan `failed`.
- MOBSF upload/poll: up to 3 retries for 5xx; poll timeout 30 min (configurable).
- Agent loop: 1 retry on transient LLM provider errors.
- Notifications: send attempts logged in `notifications` table. **Failed sends are not auto-retried** across runs (would cause duplicates). Operator queries the table for unsent notifications.

### Observability

- Per-scan structured log: `reports/<platform>/<id>/<version>/scan.log` (JSONL).
- Global run log: `./harness.log`, one line per app per stage transition.
- `mobsf-harness status <id>` prints scan history.

### Safety rails

- Max 200 MB per APK/IPA download (configurable). Reject larger.
- Max `max_turns` agent turns (default 12).
- Max total tokens per agent session (default 100k; configurable).
- Env-sourced secrets never written to `scan.log` or notifications.

### Out of scope for v1

- Report retention / pruning. Disk will grow; revisit in a follow-up.
- Parallel scans. MOBSF doesn't benefit; adds complexity.
- Alerting on harness *self*-failures (e.g., MOBSF unreachable for the whole run). Log file + systemd journal is enough for v1.

## Testing

| Layer | Test type | Approach |
|---|---|---|
| `config.py` | Unit | Pydantic schema validation; missing env vars; unknown provider; bad platform |
| `state.py` | Unit | In-memory SQLite; round-trip all tables; uniqueness constraints |
| `fetchers/*` | Unit | Mock `subprocess` for `gplaycli`/`ipatool`; mock filesystem for drop-dir |
| `mobsf_client.py` | Unit | Recorded HTTP fixtures — upload, scan, poll, fetch |
| `tools/*` | Unit | Tool isolated with synthetic MOBSF report; schema marshalling for both Anthropic + OpenAI formats |
| `llm/*` | Unit | Fake SDK responses; verify tool-call parsing, provider differences, retry |
| `agent.py` | Unit | `FakeLLMClient` with scripted tool-call sequences; loop termination; failsafe on missing `write_summary`; bounded turns |
| `notifier.py` | Unit | Mock SMTP / mock HTTP; per-channel verification; `"any"` fan-out |
| `pipeline.py` | Integration | End-to-end with fakes at every boundary; produces real `summary.md` and real DB rows, no network |
| E2E smoke | Manual / opt-in CI | One small open-source APK, real local MOBSF, real LLM call; gated behind `MOBSF_HARNESS_E2E=1` |

**Fixtures:**

- `tests/fixtures/mobsf/` — small/medium/large scrubbed MOBSF report JSONs.
- `tests/fixtures/artifacts/` — one small APK for e2e smoke.
- `tests/fixtures/llm_transcripts/` — canned tool-call sequences.

**TDD discipline.** Per the superpowers TDD skill: tests written before implementation. The pipeline integration test drives the component interfaces — it's written first, fails because nothing exists yet, and components are built bottom-up until it passes.

**Explicitly NOT tested:**

- `gplaycli` / `ipatool` / MOBSF correctness.
- LLM response *quality* (can't be unit-tested meaningfully; validated via manual e2e and `replay-agent`).

## Open questions (none blocking v1)

- Retention policy for old reports (disk growth).
- Self-health alerting if the harness itself can't reach MOBSF or LLM provider.
- Whether to support per-app LLM provider overrides (probably yes, small addition).

## Appendix: why this shape

- **Hybrid pipeline + agent** keeps deterministic I/O in deterministic code and reserves the agent for the judgment-heavy analysis phase. Scheduled/automated contexts punish non-determinism — a tool-use-driven loop owning download + upload + poll is brittle under cron.
- **Provider abstraction with two implementations** covers every compatible endpoint with minimal code: Anthropic native (server-side tools, best fidelity) and OpenAI-compatible (via `base_url` — OpenRouter, Ollama, vLLM, LM Studio, LocalAI all collapse to the same client).
- **Pluggable web search** sidesteps the fact that Anthropic's native `web_search` server tool doesn't work through OpenRouter or local endpoints — a client-side tool works identically everywhere.
- **Config file for app list + SQLite for state** keeps the user-editable surface tiny (one YAML file) while giving the harness a real database for history and diff-based agent context.
