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
    reaped = state.reap_orphaned_scans()
    if reaped:
        click.echo(f"Recovered {reaped} orphaned scan(s) from prior run(s).", err=True)
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


@main.command("replay-agent")
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
