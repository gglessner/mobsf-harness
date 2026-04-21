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
