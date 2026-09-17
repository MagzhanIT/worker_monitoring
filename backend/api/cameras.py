from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import require_manager
from database import get_db
from db_models.camera import Camera
from db_models.camera_debug import CameraDebugSetting
from logging_config import redact_source
from schemas.camera import (
    CameraCreate,
    CameraDebugResponse,
    CameraDebugSettings,
    CameraResponse,
    CameraUpdate,
)
from services.camera_manager import camera_manager
from utilities.file_security import protect_source, reveal_source
from utilities.validation import validate_camera_source

router = APIRouter(prefix="/cameras", tags=["cameras"])


def _stored(source: str) -> str:
    return "enc:" + protect_source(source)


def _revealed(source: str) -> str:
    return reveal_source(source[4:]) if source.startswith("enc:") else source


def _public(camera: Camera) -> CameraResponse:
    data = {column.name: getattr(camera, column.name) for column in Camera.__table__.columns}
    data["source"] = redact_source(_revealed(camera.source))
    return CameraResponse.model_validate(data)


def _get_camera(db: Session, camera_id: int) -> Camera:
    camera = db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(404, "Camera not found")
    return camera


@router.get("", response_model=list[CameraResponse], dependencies=[Depends(require_manager)])
def list_cameras(db: Session = Depends(get_db)) -> list[CameraResponse]:
    return [_public(camera) for camera in db.scalars(select(Camera).order_by(Camera.id)).all()]


@router.post("", response_model=CameraResponse, status_code=201, dependencies=[Depends(require_manager)])
def create_camera(payload: CameraCreate, db: Session = Depends(get_db)) -> CameraResponse:
    errors = validate_camera_source(payload.source)
    if errors:
        raise HTTPException(422, errors)
    camera = Camera(**payload.model_dump(exclude={"source"}), source=_stored(payload.source))
    db.add(camera)
    db.commit()
    db.refresh(camera)
    return _public(camera)


@router.get("/{camera_id}", response_model=CameraResponse, dependencies=[Depends(require_manager)])
def get_camera(camera_id: int, db: Session = Depends(get_db)) -> CameraResponse:
    return _public(_get_camera(db, camera_id))


@router.put("/{camera_id}", response_model=CameraResponse, dependencies=[Depends(require_manager)])
def update_camera(camera_id: int, payload: CameraUpdate, db: Session = Depends(get_db)) -> CameraResponse:
    errors = validate_camera_source(payload.source)
    if errors:
        raise HTTPException(422, errors)
    camera = _get_camera(db, camera_id)
    old_geometry = (camera.source, camera.reference_width, camera.reference_height, camera.rotation, camera.mirror)
    for key, value in payload.model_dump(exclude={"source"}).items():
        setattr(camera, key, value)
    camera.source = _stored(payload.source)
    new_geometry = (camera.source, camera.reference_width, camera.reference_height, camera.rotation, camera.mirror)
    if new_geometry != old_geometry:
        camera.config_version += 1
    db.commit()
    db.refresh(camera)
    return _public(camera)


@router.delete("/{camera_id}", status_code=204, dependencies=[Depends(require_manager)])
def delete_camera(camera_id: int, db: Session = Depends(get_db)) -> Response:
    camera = _get_camera(db, camera_id)
    camera_manager.stop(camera_id)
    db.delete(camera)
    db.commit()
    return Response(status_code=204)


@router.post("/{camera_id}/start", dependencies=[Depends(require_manager)])
def start_camera(camera_id: int, db: Session = Depends(get_db)) -> dict:
    camera = _get_camera(db, camera_id)
    return camera_manager.start(camera_id, _revealed(camera.source))


@router.post("/{camera_id}/stop", dependencies=[Depends(require_manager)])
def stop_camera(camera_id: int, db: Session = Depends(get_db)) -> dict:
    _get_camera(db, camera_id)
    return camera_manager.stop(camera_id)


@router.post("/{camera_id}/restart", dependencies=[Depends(require_manager)])
def restart_camera(camera_id: int, db: Session = Depends(get_db)) -> dict:
    camera = _get_camera(db, camera_id)
    return camera_manager.restart(camera_id, _revealed(camera.source))


@router.get("/{camera_id}/status", dependencies=[Depends(require_manager)])
def camera_status(camera_id: int, db: Session = Depends(get_db)) -> dict:
    _get_camera(db, camera_id)
    return camera_manager.status(camera_id)


@router.get(
    "/{camera_id}/activity-diagnostics",
    dependencies=[Depends(require_manager)],
)
def activity_diagnostics(camera_id: int, db: Session = Depends(get_db)) -> dict:
    _get_camera(db, camera_id)
    return camera_manager.diagnostics(camera_id)


def _jpeg(camera_id: int, view: str = "normal") -> bytes | None:
    service = camera_manager.get(camera_id)
    frame = service.frame(view) if service else None
    if frame is None:
        packet = service.frames.latest() if service else None
        frame = packet.frame if packet else None
    if frame is None:
        return None
    try:
        import cv2
        ok, encoded = cv2.imencode(".jpg", frame)
        return encoded.tobytes() if ok else None
    except Exception:
        return None


@router.get("/{camera_id}/frame.jpg", dependencies=[Depends(require_manager)])
def current_frame(
    camera_id: int,
    view: str = Query(default="normal", pattern="^(normal|test|auto)$"),
    db: Session = Depends(get_db),
) -> Response:
    _get_camera(db, camera_id)
    payload = _jpeg(camera_id, view)
    if payload is None:
        raise HTTPException(503, "No current frame is available")
    return Response(payload, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/{camera_id}/stream.mjpeg", dependencies=[Depends(require_manager)])
def stream(
    camera_id: int,
    view: str = Query(default="normal", pattern="^(normal|test|auto)$"),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    _get_camera(db, camera_id)
    def frames():
        last = None
        import time
        while True:
            service = camera_manager.get(camera_id)
            packet = service.frames.latest() if service else None
            if packet and packet.sequence_id != last:
                image = _jpeg(camera_id, view)
                if image:
                    last = packet.sequence_id
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + image + b"\r\n"
            time.sleep(0.08)
    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")


def _debug_values(row: CameraDebugSetting | None) -> dict:
    defaults = CameraDebugSettings()
    if row is None:
        return defaults.model_dump()
    return {
        key: getattr(row, key)
        for key in CameraDebugSettings.model_fields
    }


@router.get(
    "/{camera_id}/debug",
    response_model=CameraDebugResponse,
    dependencies=[Depends(require_manager)],
)
def get_debug_settings(camera_id: int, db: Session = Depends(get_db)):
    _get_camera(db, camera_id)
    return CameraDebugResponse(
        camera_id=camera_id,
        **_debug_values(db.get(CameraDebugSetting, camera_id)),
    )


@router.put(
    "/{camera_id}/debug",
    response_model=CameraDebugResponse,
    dependencies=[Depends(require_manager)],
)
def update_debug_settings(
    camera_id: int,
    payload: CameraDebugSettings,
    db: Session = Depends(get_db),
):
    _get_camera(db, camera_id)
    row = db.get(CameraDebugSetting, camera_id)
    if row is None:
        row = CameraDebugSetting(camera_id=camera_id, **payload.model_dump())
        db.add(row)
    else:
        for key, value in payload.model_dump().items():
            setattr(row, key, value)
    db.commit()
    camera_manager.set_debug_settings(camera_id, payload.model_dump())
    return CameraDebugResponse(camera_id=camera_id, **payload.model_dump())
