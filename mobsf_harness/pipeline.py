from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from mobsf_harness.agent import run_agent
from mobsf_harness.config import AppEntry, Config
from mobsf_harness.fetchers.base import Fetcher
from mobsf_harness.llm.types import LlmClient
from mobsf_harness.mobsf_client import MobsfClient  # noqa: F401 (typing aid)
from mobsf_harness.notifier import Notifier
from mobsf_harness.state import StateStore
from mobsf_harness.tools import build_tool_registry
from mobsf_harness.tools.search import web_search_tool


log = logging.getLogger("mobsf_harness.pipeline")


@dataclass
class PipelineResult:
    status: str
    reason: str = ""
    scan_id: int | None = None


@dataclass
class PipelineDeps:
    state: StateStore
    mobsf_client: Any
    fetcher_factory: Callable[[AppEntry], Fetcher]
    llm_client: LlmClient
    reports_root: Path
    notifier: Notifier | None = None


_SEVERITY_ORDER = ["info", "low", "medium", "high", "critical"]


def _severity_rank(sev: str) -> int:
    try:
        return _SEVERITY_ORDER.index(sev)
    except ValueError:
        return 0


def _flatten_findings(report: dict[str, Any]) -> list[tuple[str, str, str, dict]]:
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

        for key, sev, title, raw in _flatten_findings(report_json):
            state.add_finding(scan_rec.id, key, sev, title, raw)

        state.update_scan_status(scan_rec.id, "analyzing")

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
