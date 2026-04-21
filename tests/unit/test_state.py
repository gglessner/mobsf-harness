import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mobsf_harness.state import (
    AppRecord,
    FindingRecord,
    NotificationRecord,
    ScanRecord,
    StateStore,
)


@pytest.fixture
def store(tmp_path: Path) -> StateStore:
    s = StateStore(tmp_path / "state.sqlite")
    s.initialize()
    return s


def test_get_or_create_app_is_idempotent(store: StateStore):
    a1 = store.get_or_create_app("android", "com.example", "play_store")
    a2 = store.get_or_create_app("android", "com.example", "play_store")
    assert a1.id == a2.id


def test_record_scan_and_fetch_latest(store: StateStore):
    app = store.get_or_create_app("android", "com.example", "play_store")
    scan = store.create_scan(
        app_id=app.id,
        version_name="1.2.3",
        version_code="4501",
        sha256="abc123",
        report_dir="reports/android/com.example/1.2.3-4501",
    )
    assert scan.status == "queued"
    store.update_scan_status(scan.id, "done", finished_at=datetime.now(timezone.utc))

    latest = store.latest_completed_scan(app.id)
    assert latest is not None
    assert latest.version_code == "4501"
    assert latest.status == "done"


def test_latest_completed_scan_skips_failed(store: StateStore):
    app = store.get_or_create_app("android", "com.example", "play_store")
    s1 = store.create_scan(app.id, "1.0", "1", "h1", "r1")
    store.update_scan_status(s1.id, "done", finished_at=datetime.now(timezone.utc))
    s2 = store.create_scan(app.id, "1.1", "2", "h2", "r2")
    store.update_scan_status(s2.id, "failed", error_message="boom")

    latest = store.latest_completed_scan(app.id)
    assert latest.id == s1.id


def test_same_sha_allowed_across_scans(store: StateStore):
    """Historically UNIQUE(app_id, sha256) blocked retries after a crash or
    --force-rescan. That constraint was dropped; same-sha rows are now allowed
    so the pipeline can rescan the same artifact and keep audit history."""
    app = store.get_or_create_app("android", "com.example", "play_store")
    a = store.create_scan(app.id, "1.0", "1", "same_hash", "r1")
    b = store.create_scan(app.id, "1.1", "2", "same_hash", "r2")
    assert a.id != b.id
    assert a.sha256 == b.sha256 == "same_hash"


def test_legacy_sha_unique_is_migrated_away(tmp_path: Path):
    """A DB created with the old UNIQUE(app_id, sha256) constraint should be
    silently migrated on initialize() so new inserts don't fail.

    Crucially, the legacy DB also has findings/notifications rows whose FKs
    point at scans(id) — rebuilding the scans table without disabling FK
    enforcement would fail with IntegrityError. This test exercises that path.
    """
    import sqlite3
    db = tmp_path / "legacy.sqlite"
    legacy = sqlite3.connect(db)
    legacy.executescript(
        """
        CREATE TABLE apps (id INTEGER PRIMARY KEY, platform TEXT NOT NULL,
          identifier TEXT NOT NULL, source TEXT NOT NULL,
          first_seen TEXT NOT NULL, last_checked TEXT,
          UNIQUE(platform, identifier));
        CREATE TABLE scans (id INTEGER PRIMARY KEY,
          app_id INTEGER NOT NULL REFERENCES apps(id),
          version_name TEXT, version_code TEXT, sha256 TEXT NOT NULL,
          started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
          error_message TEXT, report_dir TEXT, mobsf_scan_hash TEXT,
          UNIQUE(app_id, sha256));
        CREATE TABLE findings (id INTEGER PRIMARY KEY,
          scan_id INTEGER NOT NULL REFERENCES scans(id),
          finding_key TEXT NOT NULL, severity TEXT NOT NULL,
          title TEXT NOT NULL, raw TEXT NOT NULL);
        CREATE TABLE notifications (id INTEGER PRIMARY KEY,
          scan_id INTEGER NOT NULL REFERENCES scans(id),
          channel TEXT NOT NULL, severity TEXT NOT NULL,
          body TEXT NOT NULL, sent_at TEXT, error_message TEXT);
        INSERT INTO apps(platform, identifier, source, first_seen)
          VALUES ('android', 'com.e', 'play_store', '2026-04-20T00:00:00+00:00');
        INSERT INTO scans(app_id, version_name, version_code, sha256,
                          started_at, status, report_dir)
          VALUES (1, '1.0', '1', 'h', '2026-04-20T00:00:00+00:00', 'failed', 'r1');
        INSERT INTO findings(scan_id, finding_key, severity, title, raw)
          VALUES (1, 'RULE_X', 'high', 't', '{}');
        INSERT INTO notifications(scan_id, channel, severity, body)
          VALUES (1, 'log', 'high', 'body');
        """
    )
    legacy.commit()
    legacy.close()

    store = StateStore(db)
    store.initialize()   # must migrate without breaking FKs

    # Child rows survived the swap
    assert len(store.findings_for_scan(1)) == 1
    assert len(store.notifications_for_scan(1)) == 1
    # And the UNIQUE is gone: same-sha insert works
    store.create_scan(1, "1.0", "1", "h", "r1-retry")


def test_findings_roundtrip(store: StateStore):
    app = store.get_or_create_app("android", "com.example", "play_store")
    scan = store.create_scan(app.id, "1.0", "1", "h", "r")
    store.add_finding(scan.id, "RULE_A@MainActivity", "high", "exported", {"raw": 1})
    store.add_finding(scan.id, "RULE_B@Foo", "medium", "tls", {"raw": 2})

    found = store.findings_for_scan(scan.id)
    assert len(found) == 2
    assert {f.finding_key for f in found} == {"RULE_A@MainActivity", "RULE_B@Foo"}


def test_prior_finding_history(store: StateStore):
    app = store.get_or_create_app("android", "com.example", "play_store")
    older = store.create_scan(app.id, "1.0", "1", "h1", "r1")
    store.update_scan_status(older.id, "done", finished_at=datetime.now(timezone.utc))
    store.add_finding(older.id, "RULE_A", "high", "t", {})
    newer = store.create_scan(app.id, "1.1", "2", "h2", "r2")
    store.update_scan_status(newer.id, "done", finished_at=datetime.now(timezone.utc))

    history = store.prior_finding_history(app.id, "RULE_A", before_scan_id=newer.id)

    assert len(history) == 1
    assert history[0].scan_id == older.id


def test_record_notification(store: StateStore):
    app = store.get_or_create_app("android", "com.example", "play_store")
    scan = store.create_scan(app.id, "1.0", "1", "h", "r")
    n = store.record_notification(scan.id, "log", "high", "saw new issue")
    assert n.sent_at is None
    store.mark_notification_sent(n.id)
    refetched = store.notifications_for_scan(scan.id)[0]
    assert refetched.sent_at is not None


def test_reap_orphaned_scans_marks_transient_as_failed(store: StateStore):
    app = store.get_or_create_app("android", "com.example", "play_store")
    s_done = store.create_scan(app.id, "1.0", "1", "h1", "r1")
    store.update_scan_status(s_done.id, "done", finished_at=datetime.now(timezone.utc))
    s_failed = store.create_scan(app.id, "1.1", "2", "h2", "r2")
    store.update_scan_status(s_failed.id, "failed", error_message="existing")
    s_queued = store.create_scan(app.id, "1.2", "3", "h3", "r3")
    # leave s_queued as 'queued'
    s_scanning = store.create_scan(app.id, "1.3", "4", "h4", "r4")
    store.update_scan_status(s_scanning.id, "scanning")
    s_analyzing = store.create_scan(app.id, "1.4", "5", "h5", "r5")
    store.update_scan_status(s_analyzing.id, "analyzing")

    reaped = store.reap_orphaned_scans()

    assert reaped == 3
    # transient rows now failed
    for sid in (s_queued.id, s_scanning.id, s_analyzing.id):
        s = store.get_scan(sid)
        assert s.status == "failed"
        assert "interrupted" in (s.error_message or "").lower()
        assert s.finished_at is not None
    # done and failed rows untouched
    assert store.get_scan(s_done.id).status == "done"
    assert store.get_scan(s_failed.id).error_message == "existing"


def test_reap_orphaned_scans_returns_zero_when_clean(store: StateStore):
    app = store.get_or_create_app("android", "com.example", "play_store")
    s = store.create_scan(app.id, "1.0", "1", "h", "r")
    store.update_scan_status(s.id, "done", finished_at=datetime.now(timezone.utc))
    assert store.reap_orphaned_scans() == 0
