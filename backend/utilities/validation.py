from __future__ import annotations

from urllib.parse import urlsplit

from utilities.geometry import polygon_area, polygon_self_intersects

SUPPORTED_SCHEMES = {"rtsp", "rtsps", "file", "webcam", "demo"}


def validate_camera_source(source: str) -> list[str]:
    errors: list[str] = []
    try:
        parts = urlsplit(source)
    except ValueError:
        return ["Invalid camera source URL"]
    if parts.scheme.lower() not in SUPPORTED_SCHEMES:
        errors.append(f"Unsupported source scheme: {parts.scheme or 'missing'}")
    if parts.scheme in {"rtsp", "rtsps"} and not parts.hostname:
        errors.append("RTSP source requires a host")
    if parts.scheme == "webcam" and not (parts.netloc or parts.path):
        errors.append("Webcam source requires a device number")
    if parts.scheme == "demo" and (parts.netloc or parts.path.lstrip("/")) != "sample":
        errors.append("Only demo://sample is supported")
    return errors


def validate_polygon(points: list[tuple[float, float]], min_area: float, max_area: float) -> list[str]:
    errors: list[str] = []
    if len(set(points)) < 3:
        errors.append("Polygon requires at least 3 unique points")
        return errors
    if any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in points):
        errors.append("All polygon coordinates must be between 0 and 1")
    if polygon_self_intersects(points):
        errors.append("Polygon must not self-intersect")
    area = polygon_area(points)
    if not min_area <= area <= max_area:
        errors.append(f"Polygon area must be between {min_area} and {max_area}")
    return errors

