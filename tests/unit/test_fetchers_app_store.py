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
    assert info.version_code == "3.4.5"


@patch("mobsf_harness.fetchers.app_store.subprocess.run")
def test_latest_version_raises_when_no_app(mock_run):
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = '{"apps":[]}'
    with pytest.raises(FetchError):
        AppStoreFetcher().latest_version(_app())


@patch("mobsf_harness.fetchers.app_store.subprocess.run")
def test_fetch_downloads_and_hashes(mock_run, tmp_path: Path):
    def fake_run(cmd, **kw):
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


@patch("mobsf_harness.fetchers.app_store.subprocess.run")
def test_latest_version_raises_on_timeout(mock_run):
    import subprocess
    mock_run.side_effect = subprocess.TimeoutExpired(cmd=["ipatool"], timeout=60)

    with pytest.raises(FetchError, match="timed out"):
        AppStoreFetcher().latest_version(_app())
