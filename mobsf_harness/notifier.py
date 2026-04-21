from __future__ import annotations

import json
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import httpx

from mobsf_harness.config import EmailChannel, LogChannel, NotificationsConfig, WebhookChannel


class Notifier:
    def __init__(self, cfg: NotificationsConfig) -> None:
        self._cfg = cfg

    def send(self, intent: dict) -> None:
        channel = intent["channel"]
        if channel == "any":
            self._send_any(intent)
            return
        if channel == "log":
            self._send_log(intent)
            return
        if channel == "webhook":
            self._send_webhook(intent)
            return
        if channel == "email":
            self._send_email(intent)
            return
        raise ValueError(f"unknown channel: {channel}")

    def _send_any(self, intent: dict) -> None:
        if self._cfg.log:
            self._send_log(intent)
        if self._cfg.webhook:
            self._send_webhook(intent)
        if self._cfg.email:
            self._send_email(intent)

    def _send_log(self, intent: dict) -> None:
        if not self._cfg.log:
            raise ValueError("log channel not configured")
        path = Path(self._cfg.log.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {**intent, "ts": datetime.now(timezone.utc).isoformat()}
        with path.open("a") as fp:
            fp.write(json.dumps(record) + "\n")

    def _send_webhook(self, intent: dict) -> None:
        if not self._cfg.webhook:
            raise ValueError("webhook channel not configured")
        wh: WebhookChannel = self._cfg.webhook
        rsp = httpx.post(wh.url, json=intent, headers=wh.headers or {}, timeout=10.0)
        rsp.raise_for_status()

    def _send_email(self, intent: dict) -> None:
        if not self._cfg.email:
            raise ValueError("email channel not configured")
        cfg: EmailChannel = self._cfg.email
        msg = EmailMessage()
        msg["Subject"] = f"[MOBSF {intent['severity']}] {intent['title']}"
        msg["From"] = cfg.from_addr
        msg["To"] = ", ".join(cfg.to_addrs)
        msg.set_content(intent["body"])
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port) as s:
            if cfg.username and cfg.password:
                s.starttls()
                s.login(cfg.username, cfg.password)
            s.send_message(msg)
