import json
import socket
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

from config import settings


def _port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.5)
        return connection.connect_ex((host, port)) == 0


def _same_backend_is_running(port: int) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=1.5) as response:
            payload = json.load(response)
        return payload.get("status") == "ok" and payload.get("app") == settings.app_name
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return False


if __name__ == "__main__":
    if _port_is_open("127.0.0.1", settings.app_port):
        if _same_backend_is_running(settings.app_port):
            print(
                f"{settings.app_name} is already running at "
                f"http://localhost:{settings.app_port}. No second server was started."
            )
            raise SystemExit(0)
        print(
            f"Port {settings.app_port} is already used by another application. "
            "Stop that application or choose another APP_PORT in .env."
        )
        raise SystemExit(2)
    uvicorn.run("app:app", host=settings.app_host, port=settings.app_port, reload=settings.app_reload)
