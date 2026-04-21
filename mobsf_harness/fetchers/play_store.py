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

_SEARCH_TIMEOUT_S = 60
_DOWNLOAD_TIMEOUT_S = 600


def _run_gplaycli(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise FetchError(f"gplaycli timed out after {timeout}s: {' '.join(args)}") from e


class PlayStoreFetcher:
    def latest_version(self, app: AppEntry) -> VersionInfo:
        proc = _run_gplaycli(["gplaycli", "-s", app.identifier], _SEARCH_TIMEOUT_S)
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
        proc = _run_gplaycli(
            ["gplaycli", "-d", app.identifier, "-f", str(dest_dir)],
            _DOWNLOAD_TIMEOUT_S,
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
        try:
            info = self.latest_version(app)
            version_name = info.version_name
        except Exception:
            version_name = version_code
        return FetchResult(
            artifact_path=out,
            sha256=sha256_file(out),
            version_name=version_name,
            version_code=version_code,
        )
