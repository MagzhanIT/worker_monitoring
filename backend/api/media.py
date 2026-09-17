from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from api.auth import require_manager
from utilities.file_security import MEDIA_ROOTS, safe_media_path

router = APIRouter(prefix="/media", tags=["protected media"], dependencies=[Depends(require_manager)])


def _serve(kind: str, media_id: str):
    try:
        path = safe_media_path(MEDIA_ROOTS[kind], media_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not path.is_file():
        raise HTTPException(404, "Media not found")
    return FileResponse(path, headers={"Cache-Control": "private, no-store"})


@router.get("/snapshots/{safe_media_id:path}")
def snapshot(safe_media_id: str):
    return _serve("snapshots", safe_media_id)


@router.get("/evidence/{safe_media_id:path}")
def evidence(safe_media_id: str):
    return _serve("evidence", safe_media_id)

