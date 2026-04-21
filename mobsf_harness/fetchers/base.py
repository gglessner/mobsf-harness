from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from mobsf_harness.config import AppEntry


class FetchError(Exception):
    pass


@dataclass
class VersionInfo:
    version_name: str
    version_code: str


@dataclass
class FetchResult:
    artifact_path: Path
    sha256: str
    version_name: str
    version_code: str


class Fetcher(Protocol):
    def latest_version(self, app: AppEntry) -> VersionInfo: ...
    def fetch(self, app: AppEntry, *, version_code: str, dest_dir: Path) -> FetchResult: ...


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_to(src: Path, dest_dir: Path, filename: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dst = dest_dir / filename
    shutil.copy2(src, dst)
    return dst
