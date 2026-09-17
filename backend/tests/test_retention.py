from datetime import datetime, timedelta
from pathlib import Path

from services import retention_service


def test_dry_run_and_actual_cleanup(monkeypatch, tmp_path):
    snapshots = tmp_path / "worker_snapshots"
    evidence = tmp_path / "evidence"
    debug = tmp_path / "debug_phone_misses"
    for folder in (snapshots, evidence, debug):
        folder.mkdir()
    old = snapshots / "old.jpg"
    old.write_bytes(b"x")
    timestamp = (datetime.now() - timedelta(days=60)).timestamp()
    import os
    os.utime(old, (timestamp, timestamp))
    monkeypatch.setattr(retention_service, "BACKEND_DIR", tmp_path)
    assert str(old) in retention_service.cleanup(dry_run=True)
    assert old.exists()
    retention_service.cleanup(dry_run=False)
    assert not old.exists()


def test_active_session_files_are_preserved(monkeypatch, tmp_path):
    folder = tmp_path / "evidence" / "active-session"
    folder.mkdir(parents=True)
    (folder / ".active").write_text("")
    old = folder / "clip.mp4"; old.write_bytes(b"x")
    timestamp = (datetime.now() - timedelta(days=60)).timestamp()
    import os
    os.utime(old, (timestamp, timestamp))
    monkeypatch.setattr(retention_service, "BACKEND_DIR", tmp_path)
    retention_service.cleanup(dry_run=False)
    assert old.exists()

