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


def test_artifact_hash_is_unique_per_app(store: StateStore):
    app = store.get_or_create_app("android", "com.example", "play_store")
    store.create_scan(app.id, "1.0", "1", "same_hash", "r1")
    with pytest.raises(Exception):
        store.create_scan(app.id, "1.1", "2", "same_hash", "r2")


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
