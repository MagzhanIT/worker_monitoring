from pathlib import Path

import pytest

from api.auth import hash_password, verify_password
from logging_config import redact_source
from utilities.file_security import safe_media_path


def test_password_hashing():
    value = hash_password("correct horse battery staple")
    assert value != "correct horse battery staple"
    assert verify_password("correct horse battery staple", value)
    assert not verify_password("wrong", value)


def test_path_traversal_blocked(tmp_path):
    with pytest.raises(ValueError):
        safe_media_path(tmp_path, "../secret.txt")
    assert safe_media_path(tmp_path, "date/clip.mp4") == tmp_path / "date" / "clip.mp4"


def test_rtsp_password_redaction():
    value = redact_source("rtsp://worker:very-secret@camera.local/live")
    assert "very-secret" not in value and "worker" not in value

