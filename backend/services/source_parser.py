from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from urllib.parse import parse_qs, unquote, urlsplit

from config import BACKEND_DIR, settings
from utilities.validation import validate_camera_source


@dataclass(frozen=True)
class ParsedSource:
    kind: str
    capture_value: str | int
    loop: bool = False
    realtime: bool = False


def _query_bool(query: dict[str, list[str]], name: str, default: bool) -> bool:
    values = query.get(name)
    if not values:
        return default
    return values[-1].strip().lower() not in {"0", "false", "no", "off"}


def parse_source(source: str) -> ParsedSource:
    errors = validate_camera_source(source)
    if errors:
        raise ValueError("; ".join(errors))
    parts = urlsplit(source)
    scheme = parts.scheme.lower()
    query = parse_qs(parts.query)
    if scheme in {"rtsp", "rtsps"}:
        return ParsedSource(scheme, source)
    if scheme == "webcam":
        value = (parts.netloc or parts.path).strip("/")
        if not value.isdigit():
            raise ValueError("Webcam device must be a non-negative integer")
        return ParsedSource("webcam", int(value))
    if scheme == "demo":
        return ParsedSource(
            "demo",
            str(BACKEND_DIR / "demo" / "demo_source.mp4"),
            loop=_query_bool(query, "loop", True),
            realtime=_query_bool(query, "realtime", True),
        )
    raw = unquote((parts.netloc + parts.path) if parts.netloc else parts.path)
    if len(raw) >= 3 and raw[0] == "/" and raw[2] == ":":
        raw = raw[1:]
    capture = str(PureWindowsPath(raw)) if len(raw) >= 2 and raw[1] == ":" else raw
    return ParsedSource(
        "file",
        capture,
        loop=_query_bool(query, "loop", settings.local_video_loop),
        realtime=_query_bool(query, "realtime", settings.local_video_realtime),
    )
