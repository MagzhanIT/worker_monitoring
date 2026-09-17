from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import select

from config import settings
from api.worker_identities import assign_session, list_worker_identities
from db_models.camera import Camera
from db_models.camera_session import CameraSession
from db_models.worker_identity import (
    WorkerAppearanceSignature,
    WorkerIdentityLink,
)
from db_models.worker_session import WorkerSession
from services.global_identity_service import (
    GlobalWorkerIdentityService,
    clothing_descriptor,
    cosine_distance,
    decode_descriptor,
    ranked_identity_matches,
)
from schemas.worker_identity import IdentityAssignmentRequest


def _crop(base_color=(60, 180, 220)):
    image = np.zeros((180, 80, 3), dtype=np.uint8)
    image[:] = base_color
    image[20:90, 8:72] = (230, 230, 230)
    image[90:170, 8:35] = (30, 30, 40)
    image[90:170, 45:72] = (70, 60, 50)
    image[::8, :] = (10, 10, 10)
    return image


def _seed_sessions(db):
    now = datetime(2026, 7, 25, 9, 0, tzinfo=UTC)
    db.add_all(
        [
            Camera(id=1, name="Front", source="demo://front"),
            Camera(id=2, name="Back", source="demo://back"),
            CameraSession(id="CS-A", camera_id=1, source_type="demo"),
            CameraSession(id="CS-B", camera_id=2, source_type="demo"),
            WorkerSession(
                id="WS-A",
                camera_id=1,
                camera_session_id="CS-A",
                track_id=1,
                display_name="Worker 1",
                first_seen=now,
                last_seen=now + timedelta(seconds=10),
            ),
            WorkerSession(
                id="WS-B",
                camera_id=2,
                camera_session_id="CS-B",
                track_id=2,
                display_name="Worker 1",
                first_seen=now + timedelta(seconds=15),
                last_seen=now + timedelta(seconds=25),
            ),
        ]
    )
    db.commit()
    return now


def _resolve(service, db, session_id, camera_id, crop, now, mono_start):
    result = None
    for index in range(3):
        result = service.observe(
            db,
            worker_session_id=session_id,
            camera_id=camera_id,
            person_crop=crop,
            observed_at=now + timedelta(seconds=index),
            now_monotonic=mono_start + index,
        )
    db.commit()
    return result


def test_clothing_descriptor_is_stable_and_ranked_with_margin():
    first = clothing_descriptor(_crop())
    similar = clothing_descriptor(_crop())
    different = clothing_descriptor(_crop((180, 40, 40)))
    assert first is not None and len(first) > 500
    assert cosine_distance(first, similar) < cosine_distance(first, different)
    ranked = ranked_identity_matches(
        first, [("same", [similar]), ("different", [different])]
    )
    assert ranked[0][0] == "same"


def test_same_worker_recovers_global_id_on_second_camera(db, monkeypatch):
    now = _seed_sessions(db)
    monkeypatch.setattr(settings, "global_worker_id_min_quality", 0.0)
    service = GlobalWorkerIdentityService()
    first = _resolve(service, db, "WS-A", 1, _crop(), now, 0)
    assert first.identity_id and first.match_status == "new_identity"
    service.close_session("WS-A")
    second = _resolve(
        service, db, "WS-B", 2, _crop(), now + timedelta(seconds=15), 20
    )
    assert second.identity_id == first.identity_id
    assert second.match_status == "appearance_matched"
    links = db.scalars(select(WorkerIdentityLink)).all()
    assert {link.worker_identity_id for link in links} == {first.identity_id}
    signature = db.scalar(select(WorkerAppearanceSignature))
    assert not signature.descriptor_ciphertext.startswith("[")
    assert decode_descriptor(signature.descriptor_ciphertext) is not None


def test_active_identity_on_another_camera_is_not_silently_merged(db, monkeypatch):
    now = _seed_sessions(db)
    monkeypatch.setattr(settings, "global_worker_id_min_quality", 0.0)
    service = GlobalWorkerIdentityService()
    first = _resolve(service, db, "WS-A", 1, _crop(), now, 0)
    assert first.identity_id
    second = _resolve(service, db, "WS-B", 2, _crop(), now, 2)
    assert second.identity_id is None
    assert second.match_status == "pending_active_conflict"
    assert db.get(WorkerIdentityLink, "WS-B") is None


def test_manager_can_confirm_second_camera_session(db, monkeypatch):
    now = _seed_sessions(db)
    monkeypatch.setattr(settings, "global_worker_id_min_quality", 0.0)
    service = GlobalWorkerIdentityService()
    first = _resolve(service, db, "WS-A", 1, _crop(), now, 0)

    result = assign_session(
        first.identity_id,
        "WS-B",
        IdentityAssignmentRequest(note="Manager verified the same worker"),
        db,
    )

    assert result["success"]
    link = db.get(WorkerIdentityLink, "WS-B")
    assert link.worker_identity_id == first.identity_id
    assert link.match_status == "manager_confirmed"
    identities = list_worker_identities(report_date=now.date(), db=db)
    assert identities[0].session_count == 2
    assert identities[0].camera_ids == [1, 2]
