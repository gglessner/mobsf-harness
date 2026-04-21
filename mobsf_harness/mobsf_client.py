from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


class MobsfError(Exception):
    pass


@dataclass
class ScanStatus:
    hash: str
    file_name: str
    scan_type: str


def _retriable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return 500 <= exc.response.status_code < 600
    return isinstance(exc, httpx.TransportError)


_retry = retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=4),
    reraise=True,
)


class MobsfClient:
    """Thin REST client for MOBSF v4+."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 60.0,
        scan_timeout: float = 1800.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": api_key}
        self._client = httpx.Client(timeout=timeout)
        self._scan_timeout = scan_timeout

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "MobsfClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def upload(self, path: Path) -> str:
        return self._upload_once(path)

    def scan(self, hash_: str, *, re_scan: bool = False) -> str:
        # Use a long timeout — MOBSF /api/v1/scan is synchronous and can take 30 min on large APKs.
        self._post(
            "/api/v1/scan",
            data={"hash": hash_, "re_scan": "1" if re_scan else "0"},
            timeout=self._scan_timeout,
        )
        return hash_

    def report_json(self, hash_: str) -> dict[str, Any]:
        return self._post("/api/v1/report_json", data={"hash": hash_}).json()

    def download_pdf(self, hash_: str, out_path: Path) -> None:
        resp = self._post("/api/v1/download_pdf", data={"hash": hash_})
        Path(out_path).write_bytes(resp.content)

    @_retry
    def _upload_once(self, path: Path) -> str:
        with path.open("rb") as fp:
            resp = self._client.post(
                f"{self._base}/api/v1/upload",
                headers=self._headers,
                files={"file": (path.name, fp, "application/octet-stream")},
            )
        self._raise_for_status(resp)
        return resp.json()["hash"]

    @_retry
    def _post(
        self,
        endpoint: str,
        *,
        data: dict[str, str],
        timeout: float | None = None,
    ) -> httpx.Response:
        resp = self._client.post(
            f"{self._base}{endpoint}",
            headers=self._headers,
            data=data,
            timeout=timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT,
        )
        self._raise_for_status(resp)
        return resp

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            if 500 <= resp.status_code < 600:
                raise httpx.HTTPStatusError(
                    f"{resp.status_code}", request=resp.request, response=resp
                )
            raise MobsfError(f"MOBSF returned {resp.status_code}: {resp.text[:200]}")
