from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import jwt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from api import analytics, auth, cameras, customers, events, media, reports, reviews, system, worker_identities, workers, zones
from api.auth import ALGORITHM, create_explicit_default_admin
from config import settings
from database import SessionLocal, init_db
from db_models.user import User
from logging_config import configure_logging
from services.camera_manager import camera_manager
from services.global_identity_service import purge_expired_signatures

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        if create_explicit_default_admin(db):
            logger.info("Created explicitly configured default administrator")
        removed_signatures = purge_expired_signatures(db)
        db.commit()
        if removed_signatures:
            logger.info("Removed %s expired anonymous appearance signatures", removed_signatures)
    if settings.app_secret_key == "change-me":
        logger.warning("APP_SECRET_KEY is using the development placeholder")
    yield
    camera_manager.stop_all()


app = FastAPI(
    title=settings.app_name,
    description="Pharmacy Operations Analytics using existing CCTV. Anonymous, reviewable and conservative by design.",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (auth.router, system.router, cameras.router, zones.router, workers.router, worker_identities.router, customers.router, events.router, reviews.router, analytics.router, reports.router, media.router):
    app.include_router(router)


def _websocket_authorized(token: str | None) -> bool:
    if not token:
        return False
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
        with SessionLocal() as db:
            user = db.get(User, int(payload["sub"]))
            return bool(user and user.is_active and user.role in {"manager", "admin"})
    except Exception:
        return False


@app.websocket("/ws/cameras/{camera_id}")
async def monitoring_socket(websocket: WebSocket, camera_id: int):
    await websocket.accept()
    try:
        auth_message = await asyncio.wait_for(websocket.receive_json(), timeout=5)
        token = auth_message.get("token") if isinstance(auth_message, dict) else None
        if not _websocket_authorized(token):
            await websocket.close(code=4401)
            return
        while True:
            health = camera_manager.status(camera_id)
            live = camera_manager.live(camera_id)
            await websocket.send_json({
                "camera_id": camera_id,
                "camera_health": health,
                **live,
                "processing_fps": health["processing_fps"],
                "model_status": {
                    "person": health["person_model_loaded"],
                    "pose": health["pose_model_loaded"],
                    "phone": health["phone_model_loaded"],
                },
                "report_status": "ready",
            })
            await asyncio.sleep(1)
    except (WebSocketDisconnect, TimeoutError):
        pass
