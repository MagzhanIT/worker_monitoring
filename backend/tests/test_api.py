from fastapi.testclient import TestClient

from api.auth import hash_password
from app import app
from database import get_db
from db_models.camera import Camera
from db_models.user import User


def test_cors_preflight_accepts_dynamic_local_flutter_port():
    with TestClient(app) as client:
        response = client.options(
            "/auth/login",
            headers={
                "Origin": "http://localhost:57600",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:57600"


def test_health_authentication_and_protected_route(db):
    db.add(User(username="manager", password_hash=hash_password("testing-password"), role="manager"))
    db.add(Camera(id=1, name="Counter", source="rtsp://private:secret@camera/live"))
    db.commit()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/cameras").status_code == 401
            login = client.post("/auth/login", json={"username": "manager", "password": "testing-password"})
            assert login.status_code == 200
            token = login.json()["access_token"]
            response = client.get("/cameras", headers={"Authorization": f"Bearer {token}"})
            assert response.status_code == 200
            diagnostics = client.get(
                "/cameras/1/activity-diagnostics",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert diagnostics.status_code == 200
            payload = diagnostics.json()
            assert payload == {
                "camera_id": 1,
                "workers": [],
                "customers": [],
                "camera": {},
            }
            assert "secret" not in diagnostics.text
    finally:
        app.dependency_overrides.clear()
