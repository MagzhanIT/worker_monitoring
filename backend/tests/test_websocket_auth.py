from fastapi.testclient import TestClient

from app import app


def test_websocket_authenticates_in_first_message_without_url_token(monkeypatch):
    monkeypatch.setattr("app._websocket_authorized", lambda token: token == "valid-token")
    with TestClient(app) as client:
        with client.websocket_connect("/ws/cameras/1") as socket:
            socket.send_json({"type": "auth", "token": "valid-token"})
            payload = socket.receive_json()
            assert payload["camera_id"] == 1
