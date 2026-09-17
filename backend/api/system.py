from fastapi import APIRouter

from config import settings
from services.camera_manager import camera_manager

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "maturity": "pre_production_validation_required",
    }


@router.get("/system/status")
def status() -> dict:
    return {
        "status": "ok",
        "cameras": {str(camera_id): camera_manager.status(camera_id) for camera_id in list(camera_manager._services)},
        "privacy": {"face_recognition": False, "face_embeddings": False, "customer_snapshots": False},
    }
