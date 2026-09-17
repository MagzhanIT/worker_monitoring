from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import require_manager
from database import get_db
from db_models.camera import Camera
from db_models.zone import CameraZone
from schemas.zone import ZoneInput, ZoneResponse, ZoneValidationResponse
from services.zone_service import validate_zone

router = APIRouter(prefix="/cameras/{camera_id}/zones", tags=["zones"])


def _camera(db: Session, camera_id: int) -> Camera:
    value = db.get(Camera, camera_id)
    if not value:
        raise HTTPException(404, "Camera not found")
    return value


def _validate(payload: ZoneInput) -> ZoneValidationResponse:
    valid, errors, area = validate_zone(payload.normalized_points)
    return ZoneValidationResponse(valid=valid, errors=errors, area_ratio=area)


@router.get("", response_model=list[ZoneResponse], dependencies=[Depends(require_manager)])
def list_zones(camera_id: int, db: Session = Depends(get_db)):
    _camera(db, camera_id)
    return db.scalars(select(CameraZone).where(CameraZone.camera_id == camera_id).order_by(CameraZone.id)).all()


@router.post("/validate", response_model=ZoneValidationResponse, dependencies=[Depends(require_manager)])
def validate_camera_zone(camera_id: int, payload: ZoneInput, db: Session = Depends(get_db)):
    _camera(db, camera_id)
    return _validate(payload)


@router.post("", response_model=ZoneResponse, status_code=201, dependencies=[Depends(require_manager)])
def create_zone(camera_id: int, payload: ZoneInput, db: Session = Depends(get_db)):
    camera = _camera(db, camera_id)
    result = _validate(payload)
    if not result.valid:
        raise HTTPException(422, result.errors)
    zone = CameraZone(camera_id=camera_id, camera_config_version=camera.config_version, **payload.model_dump())
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


@router.put("/{zone_id}", response_model=ZoneResponse, dependencies=[Depends(require_manager)])
def update_zone(camera_id: int, zone_id: int, payload: ZoneInput, db: Session = Depends(get_db)):
    camera = _camera(db, camera_id)
    zone = db.get(CameraZone, zone_id)
    if not zone or zone.camera_id != camera_id:
        raise HTTPException(404, "Zone not found for this camera")
    result = _validate(payload)
    if not result.valid:
        raise HTTPException(422, result.errors)
    for key, value in payload.model_dump().items():
        setattr(zone, key, value)
    zone.camera_config_version = camera.config_version
    db.commit()
    db.refresh(zone)
    return zone


@router.delete("/{zone_id}", status_code=204, dependencies=[Depends(require_manager)])
def delete_zone(camera_id: int, zone_id: int, db: Session = Depends(get_db)):
    _camera(db, camera_id)
    zone = db.get(CameraZone, zone_id)
    if not zone or zone.camera_id != camera_id:
        raise HTTPException(404, "Zone not found for this camera")
    db.delete(zone)
    db.commit()
    return Response(status_code=204)

