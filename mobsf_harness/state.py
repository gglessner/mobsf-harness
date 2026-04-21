from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS apps (
  id INTEGER PRIMARY KEY,
  platform TEXT NOT NULL,
  identifier TEXT NOT NULL,
  source TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  last_checked TEXT,
  UNIQUE(platform, identifier)
);

CREATE TABLE IF NOT EXISTS scans (
  id INTEGER PRIMARY KEY,
  app_id INTEGER NOT NULL REFERENCES apps(id),
  version_name TEXT,
  version_code TEXT,
  sha256 TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  error_message TEXT,
  report_dir TEXT,
  mobsf_scan_hash TEXT,
  UNIQUE(app_id, sha256)
);

CREATE TABLE IF NOT EXISTS findings (
  id INTEGER PRIMARY KEY,
  scan_id INTEGER NOT NULL REFERENCES scans(id),
  finding_key TEXT NOT NULL,
  severity TEXT NOT NULL,
  title TEXT NOT NULL,
  raw TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_findings_scan ON findings(scan_id);
CREATE INDEX IF NOT EXISTS idx_findings_key ON findings(finding_key);

CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY,
  scan_id INTEGER NOT NULL REFERENCES scans(id),
  channel TEXT NOT NULL,
  severity TEXT NOT NULL,
  body TEXT NOT NULL,
  sent_at TEXT,
  error_message TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AppRecord:
    id: int
    platform: str
    identifier: str
    source: str
    first_seen: str
    last_checked: str | None


@dataclass
class ScanRecord:
    id: int
    app_id: int
    version_name: str | None
    version_code: str | None
    sha256: str
    started_at: str
    finished_at: str | None
    status: str
    error_message: str | None
    report_dir: str | None
    mobsf_scan_hash: str | None


@dataclass
class FindingRecord:
    id: int
    scan_id: int
    finding_key: str
    severity: str
    title: str
    raw: dict[str, Any]


@dataclass
class NotificationRecord:
    id: int
    scan_id: int
    channel: str
    severity: str
    body: str
    sent_at: str | None
    error_message: str | None


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.row_factory = sqlite3.Row

    def initialize(self) -> None:
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # ---- apps ----
    def get_or_create_app(self, platform: str, identifier: str, source: str) -> AppRecord:
        row = self._conn.execute(
            "SELECT * FROM apps WHERE platform=? AND identifier=?",
            (platform, identifier),
        ).fetchone()
        if row is not None:
            return self._app(row)
        cur = self._conn.execute(
            "INSERT INTO apps(platform, identifier, source, first_seen) VALUES (?,?,?,?)",
            (platform, identifier, source, _now()),
        )
        row = self._conn.execute("SELECT * FROM apps WHERE id=?", (cur.lastrowid,)).fetchone()
        return self._app(row)

    def touch_app(self, app_id: int) -> None:
        self._conn.execute("UPDATE apps SET last_checked=? WHERE id=?", (_now(), app_id))

    # ---- scans ----
    def create_scan(
        self,
        app_id: int,
        version_name: str | None,
        version_code: str | None,
        sha256: str,
        report_dir: str,
    ) -> ScanRecord:
        cur = self._conn.execute(
            "INSERT INTO scans(app_id, version_name, version_code, sha256, started_at, status, report_dir) "
            "VALUES (?,?,?,?,?,?,?)",
            (app_id, version_name, version_code, sha256, _now(), "queued", report_dir),
        )
        row = self._conn.execute("SELECT * FROM scans WHERE id=?", (cur.lastrowid,)).fetchone()
        return self._scan(row)

    def update_scan_status(
        self,
        scan_id: int,
        status: str,
        *,
        finished_at: datetime | None = None,
        error_message: str | None = None,
        mobsf_scan_hash: str | None = None,
    ) -> None:
        self._conn.execute(
            "UPDATE scans SET status=?, finished_at=COALESCE(?, finished_at), "
            "error_message=COALESCE(?, error_message), mobsf_scan_hash=COALESCE(?, mobsf_scan_hash) "
            "WHERE id=?",
            (
                status,
                finished_at.isoformat() if finished_at else None,
                error_message,
                mobsf_scan_hash,
                scan_id,
            ),
        )

    def reap_orphaned_scans(self) -> int:
        """Mark any scan stuck in a transient state as failed.

        Called on run-start to recover from interrupted prior runs
        (SIGKILL, systemd timeout, OOM). Any scan row still in a
        transient state (``queued``, ``downloading``, ``scanning``,
        ``analyzing``) is flipped to ``failed`` with a clear error
        message and ``finished_at`` set to now. Returns the number of
        rows updated.
        """
        cur = self._conn.execute(
            "UPDATE scans "
            "SET status='failed', error_message=?, finished_at=? "
            "WHERE status IN ('queued','downloading','scanning','analyzing')",
            ("interrupted (recovered on startup)", _now()),
        )
        return cur.rowcount

    def latest_completed_scan(self, app_id: int) -> ScanRecord | None:
        row = self._conn.execute(
            "SELECT * FROM scans WHERE app_id=? AND status='done' ORDER BY id DESC LIMIT 1",
            (app_id,),
        ).fetchone()
        return self._scan(row) if row else None

    def get_scan(self, scan_id: int) -> ScanRecord | None:
        row = self._conn.execute("SELECT * FROM scans WHERE id=?", (scan_id,)).fetchone()
        return self._scan(row) if row else None

    # ---- findings ----
    def add_finding(
        self,
        scan_id: int,
        finding_key: str,
        severity: str,
        title: str,
        raw: dict[str, Any],
    ) -> None:
        self._conn.execute(
            "INSERT INTO findings(scan_id, finding_key, severity, title, raw) VALUES (?,?,?,?,?)",
            (scan_id, finding_key, severity, title, json.dumps(raw)),
        )

    def findings_for_scan(self, scan_id: int) -> list[FindingRecord]:
        rows = self._conn.execute(
            "SELECT * FROM findings WHERE scan_id=? ORDER BY id", (scan_id,)
        ).fetchall()
        return [self._finding(r) for r in rows]

    def prior_finding_history(
        self, app_id: int, finding_key: str, *, before_scan_id: int, limit: int = 5
    ) -> list[FindingRecord]:
        rows = self._conn.execute(
            """SELECT f.* FROM findings f
               JOIN scans s ON f.scan_id = s.id
               WHERE s.app_id=? AND f.finding_key=? AND f.scan_id < ?
               ORDER BY f.scan_id DESC LIMIT ?""",
            (app_id, finding_key, before_scan_id, limit),
        ).fetchall()
        return [self._finding(r) for r in rows]

    # ---- notifications ----
    def record_notification(
        self, scan_id: int, channel: str, severity: str, body: str
    ) -> NotificationRecord:
        cur = self._conn.execute(
            "INSERT INTO notifications(scan_id, channel, severity, body) VALUES (?,?,?,?)",
            (scan_id, channel, severity, body),
        )
        row = self._conn.execute(
            "SELECT * FROM notifications WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        return self._notification(row)

    def mark_notification_sent(self, notification_id: int) -> None:
        self._conn.execute(
            "UPDATE notifications SET sent_at=? WHERE id=?", (_now(), notification_id)
        )

    def mark_notification_failed(self, notification_id: int, error: str) -> None:
        self._conn.execute(
            "UPDATE notifications SET error_message=? WHERE id=?", (error, notification_id)
        )

    def notifications_for_scan(self, scan_id: int) -> list[NotificationRecord]:
        rows = self._conn.execute(
            "SELECT * FROM notifications WHERE scan_id=? ORDER BY id", (scan_id,)
        ).fetchall()
        return [self._notification(r) for r in rows]

    # ---- row mappers ----
    @staticmethod
    def _app(row: sqlite3.Row) -> AppRecord:
        return AppRecord(**dict(row))

    @staticmethod
    def _scan(row: sqlite3.Row) -> ScanRecord:
        return ScanRecord(**dict(row))

    @staticmethod
    def _finding(row: sqlite3.Row) -> FindingRecord:
        d = dict(row)
        d["raw"] = json.loads(d["raw"])
        return FindingRecord(**d)

    @staticmethod
    def _notification(row: sqlite3.Row) -> NotificationRecord:
        return NotificationRecord(**dict(row))
