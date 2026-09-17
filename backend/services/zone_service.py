from __future__ import annotations

from collections import deque

from config import settings
from utilities.geometry import point_in_polygon, polygon_area
from utilities.validation import validate_polygon


ZONE_PRIORITY = {
    "ignore_area": 100, "register_interaction": 90, "computer": 89, "pos": 88,
    "medicine_shelf": 87, "shelf_interaction": 85, "storage": 82,
    "cashier": 80, "service_position": 75, "waiting": 70, "break_area": 65,
    "authorized_out_of_zone": 60, "employee_area": 50, "customer_area": 40, "entrance": 30,
}


def validate_zone(points: list[tuple[float, float]]) -> tuple[bool, list[str], float]:
    errors = validate_polygon(points, settings.zone_min_area_ratio, settings.zone_max_area_ratio)
    return not errors, errors, polygon_area(points) if len(points) >= 3 else 0.0


def memberships(point: tuple[float, float], zones: list[dict]) -> tuple[list[str], str | None]:
    found = [z for z in zones if z.get("enabled", True) and point_in_polygon(point, z["normalized_points"])]
    found.sort(key=lambda zone: ZONE_PRIORITY.get(zone["zone_type"], 0), reverse=True)
    names = [zone["zone_type"] for zone in found]
    return names, names[0] if names else None


class TemporalZoneHistory:
    def __init__(self, window: int | None = None, hits: int | None = None) -> None:
        self.window = window or settings.zone_confirm_window
        self.hits = hits or settings.zone_min_confirm_hits
        self.history: dict[int, deque[set[str]]] = {}

    def update(self, track_id: int, zones: set[str]) -> set[str]:
        values = self.history.setdefault(track_id, deque(maxlen=self.window))
        values.append(zones)
        candidates = set().union(*values) if values else set()
        return {zone for zone in candidates if sum(zone in sample for sample in values) >= self.hits}

    def clear(self, track_id: int) -> None:
        self.history.pop(track_id, None)
