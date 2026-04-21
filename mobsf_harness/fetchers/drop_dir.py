from __future__ import annotations

import re
from pathlib import Path

from mobsf_harness.config import AppEntry

from .base import FetchError, FetchResult, Fetcher, VersionInfo, copy_to, sha256_file


_VERSION_DIR = re.compile(r"^(?P<name>[^-]+)-(?P<code>\d+)$")
_ARTIFACT_EXTS = (".apk", ".ipa")


def _version_dirs(root: Path) -> list[tuple[Path, VersionInfo]]:
    if not root.exists():
        raise FetchError(f"drop path does not exist: {root}")
    out: list[tuple[Path, VersionInfo]] = []
    for p in root.iterdir():
        if not p.is_dir():
            continue
        m = _VERSION_DIR.match(p.name)
        if m:
            out.append((p, VersionInfo(m["name"], m["code"])))
    if not out:
        raise FetchError(f"no <version>-<code> subdirs found in {root}")
    return out


def _first_artifact(d: Path) -> Path:
    for child in d.iterdir():
        if child.suffix.lower() in _ARTIFACT_EXTS:
            return child
    raise FetchError(f"no .apk or .ipa found in {d}")


class DropDirFetcher:
    def latest_version(self, app: AppEntry) -> VersionInfo:
        root = Path(app.drop_path)  # type: ignore[arg-type]
        dirs = _version_dirs(root)
        dirs.sort(key=lambda item: int(item[1].version_code), reverse=True)
        return dirs[0][1]

    def fetch(self, app: AppEntry, *, version_code: str, dest_dir: Path) -> FetchResult:
        root = Path(app.drop_path)  # type: ignore[arg-type]
        for p, info in _version_dirs(root):
            if info.version_code == version_code:
                src = _first_artifact(p)
                out = copy_to(src, dest_dir, "artifact" + src.suffix.lower())
                return FetchResult(
                    artifact_path=out,
                    sha256=sha256_file(out),
                    version_name=info.version_name,
                    version_code=info.version_code,
                )
        raise FetchError(f"version {version_code} not found in drop dir {root}")
