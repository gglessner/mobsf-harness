import json
from pathlib import Path

import httpx
import pytest
import respx

from mobsf_harness.mobsf_client import MobsfClient, MobsfError, ScanStatus


@pytest.fixture
def client() -> MobsfClient:
    return MobsfClient(base_url="http://mobsf.test", api_key="k")


@respx.mock
def test_upload_returns_hash(client: MobsfClient, tmp_path: Path):
    respx.post("http://mobsf.test/api/v1/upload").mock(
        return_value=httpx.Response(200, json={"hash": "h123", "scan_type": "apk", "file_name": "x.apk"})
    )
    apk = tmp_path / "x.apk"
    apk.write_bytes(b"PK\x03\x04")

    hsh = client.upload(apk)

    assert hsh == "h123"


@respx.mock
def test_upload_auth_failure_raises(client: MobsfClient, tmp_path: Path):
    respx.post("http://mobsf.test/api/v1/upload").mock(return_value=httpx.Response(401))
    apk = tmp_path / "x.apk"
    apk.write_bytes(b"x")

    with pytest.raises(MobsfError, match="401"):
        client.upload(apk)


@respx.mock
def test_scan_triggers_and_returns_hash(client: MobsfClient):
    respx.post("http://mobsf.test/api/v1/scan").mock(
        return_value=httpx.Response(200, json={"status": "success"})
    )
    result = client.scan("h123")
    assert result == "h123"


@respx.mock
def test_report_json_roundtrip(client: MobsfClient, fixtures_dir):
    report = json.loads((fixtures_dir / "mobsf" / "small_report.json").read_text())
    respx.post("http://mobsf.test/api/v1/report_json").mock(
        return_value=httpx.Response(200, json=report)
    )

    got = client.report_json("h123")

    assert got["app_name"] == "com.example.app"


@respx.mock
def test_download_pdf_writes_file(client: MobsfClient, tmp_path: Path):
    respx.post("http://mobsf.test/api/v1/download_pdf").mock(
        return_value=httpx.Response(200, content=b"%PDF-1.4 ...")
    )
    out = tmp_path / "r.pdf"

    client.download_pdf("h123", out)

    assert out.read_bytes().startswith(b"%PDF")


@respx.mock
def test_transient_5xx_retried(client: MobsfClient, tmp_path: Path):
    route = respx.post("http://mobsf.test/api/v1/upload").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, json={"hash": "ok", "scan_type": "apk", "file_name": "x"}),
        ]
    )
    apk = tmp_path / "x.apk"
    apk.write_bytes(b"x")

    assert client.upload(apk) == "ok"
    assert route.call_count == 3


@respx.mock
def test_scan_uses_long_timeout(client: MobsfClient):
    """scan() should use a longer timeout than the 60s client default."""
    import httpx as _httpx
    captured_timeouts: list = []

    def _capture(request):
        captured_timeouts.append(request.extensions.get("timeout"))
        return _httpx.Response(200, json={"status": "success"})

    respx.post("http://mobsf.test/api/v1/scan").mock(side_effect=_capture)

    client.scan("h123")

    assert captured_timeouts, "scan endpoint was never called"
    t = captured_timeouts[0]
    # httpx exposes per-request timeout as a dict with 'connect'/'read'/'write'/'pool'
    # or via the extensions dict. Read timeout should be significantly > 60s.
    read_timeout = t.get("read") if isinstance(t, dict) else None
    assert read_timeout is not None and read_timeout >= 600, f"read timeout too short: {t!r}"
