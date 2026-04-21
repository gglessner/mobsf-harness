from __future__ import annotations

import json
import subprocess
from pathlib import Path

from mobsf_harness.config import AppEntry

from .base import FetchError, FetchResult, Fetcher, VersionInfo, sha256_file


_SEARCH_TIMEOUT_S = 60
_DOWNLOAD_TIMEOUT_S = 600


def _run_ipatool(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise FetchError(f"ipatool timed out after {timeout}s: {' '.join(args)}") from e


class AppStoreFetcher:
    def latest_version(self, app: AppEntry) -> VersionInfo:
        proc = _run_ipatool(
            ["ipatool", "search", app.identifier, "--limit", "1", "--format", "json"],
            _SEARCH_TIMEOUT_S,
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
        proc = _run_ipatool(
            ["ipatool", "download", "-b", app.identifier, "-o", str(out), "--format", "json"],
            _DOWNLOAD_TIMEOUT_S,
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
