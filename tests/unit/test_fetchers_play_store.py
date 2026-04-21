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


@patch("mobsf_harness.fetchers.play_store.subprocess.run")
def test_latest_version_raises_on_timeout(mock_run):
    import subprocess
    mock_run.side_effect = subprocess.TimeoutExpired(cmd=["gplaycli"], timeout=60)

    with pytest.raises(FetchError, match="timed out"):
        PlayStoreFetcher().latest_version(_app())
