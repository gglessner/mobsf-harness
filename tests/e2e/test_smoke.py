import os
from pathlib import Path

import pytest

from mobsf_harness.agent import run_agent  # noqa: F401
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
