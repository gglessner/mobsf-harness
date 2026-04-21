from __future__ import annotations

from mobsf_harness.config import AppEntry

from .app_store import AppStoreFetcher
from .base import FetchError, FetchResult, Fetcher, VersionInfo
from .drop_dir import DropDirFetcher
from .play_store import PlayStoreFetcher


def fetcher_for(app: AppEntry) -> Fetcher:
    if app.source == "drop_dir":
        return DropDirFetcher()
    if app.source == "play_store":
        return PlayStoreFetcher()
    if app.source == "app_store":
        return AppStoreFetcher()
    raise FetchError(f"unknown source: {app.source}")


__all__ = [
    "AppStoreFetcher",
    "DropDirFetcher",
    "PlayStoreFetcher",
    "FetchError",
    "FetchResult",
    "Fetcher",
    "VersionInfo",
    "fetcher_for",
]
