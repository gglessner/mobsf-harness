# mobsf-harness

Scheduled, AI-assisted MOBSF analysis for mobile apps.

Author: Garland Glessner &lt;gglessner@gmail.com&gt;
License: GPL-3.0-or-later (see `LICENSE`)

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
