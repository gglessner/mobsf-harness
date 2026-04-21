import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from mobsf_harness.config import EmailChannel, LogChannel, NotificationsConfig, WebhookChannel
from mobsf_harness.notifier import Notifier


@pytest.fixture
def log_only(tmp_path: Path) -> tuple[Notifier, Path]:
    path = tmp_path / "n.jsonl"
    cfg = NotificationsConfig(log=LogChannel(path=str(path)))
    return Notifier(cfg), path


def test_log_channel_appends_jsonl(log_only):
    notifier, path = log_only
    notifier.send({"channel": "log", "severity": "high", "title": "t", "body": "b"})
    lines = path.read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["title"] == "t"
    notifier.send({"channel": "log", "severity": "low", "title": "t2", "body": "b2"})
    assert len(path.read_text().splitlines()) == 2


@respx.mock
def test_webhook_channel_posts(tmp_path):
    respx.post("https://hook.test/h").mock(return_value=httpx.Response(200))
    cfg = NotificationsConfig(
        log=LogChannel(path=str(tmp_path / "n.jsonl")),
        webhook=WebhookChannel(url="https://hook.test/h"),
    )
    notifier = Notifier(cfg)
    notifier.send({"channel": "webhook", "severity": "high", "title": "t", "body": "b"})
    assert respx.calls.call_count == 1


@patch("mobsf_harness.notifier.smtplib.SMTP")
def test_email_channel_sends(MockSMTP, tmp_path):
    conn = MagicMock()
    MockSMTP.return_value.__enter__.return_value = conn
    cfg = NotificationsConfig(
        log=LogChannel(path=str(tmp_path / "n.jsonl")),
        email=EmailChannel(
            smtp_host="smtp.test", smtp_port=587,
            from_addr="a@t", to_addrs=["b@t"],
            username="u", password="p",
        ),
    )
    notifier = Notifier(cfg)
    notifier.send({"channel": "email", "severity": "high", "title": "Subj", "body": "Body"})
    assert conn.send_message.called


def test_any_fans_out_to_all_enabled(tmp_path):
    with respx.mock:
        respx.post("https://hook.test/h").mock(return_value=httpx.Response(200))
        cfg = NotificationsConfig(
            log=LogChannel(path=str(tmp_path / "n.jsonl")),
            webhook=WebhookChannel(url="https://hook.test/h"),
        )
        notifier = Notifier(cfg)
        notifier.send({"channel": "any", "severity": "high", "title": "t", "body": "b"})
        assert (tmp_path / "n.jsonl").exists()
        assert respx.calls.call_count == 1


def test_disabled_channel_raises_descriptive_error(tmp_path):
    cfg = NotificationsConfig(log=LogChannel(path=str(tmp_path / "n.jsonl")))
    notifier = Notifier(cfg)
    with pytest.raises(ValueError, match="webhook.*not configured"):
        notifier.send({"channel": "webhook", "severity": "high", "title": "t", "body": "b"})
