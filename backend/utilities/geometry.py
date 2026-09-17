from __future__ import annotations

import math
from collections.abc import Iterable

BBox = tuple[float, float, float, float]
Point = tuple[float, float]


def bbox_area(box: BBox) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def iou(a: BBox, b: BBox) -> float:
    inter = bbox_area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))
    union = bbox_area(a) + bbox_area(b) - inter
    return inter / union if union > 0 else 0.0


def center(box: BBox) -> Point:
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def foot_point(box: BBox) -> Point:
    return ((box[0] + box[2]) / 2, box[3])


def distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def polygon_area(points: list[Point]) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]))) / 2


def point_in_polygon(point: Point, polygon: list[Point]) -> bool:
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        crosses = (yi > y) != (yj > y)
        if crosses and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def _orientation(a: Point, b: Point, c: Point) -> int:
    value = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])
    return 0 if abs(value) < 1e-12 else (1 if value > 0 else 2)


def segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    return _orientation(a, b, c) != _orientation(a, b, d) and _orientation(c, d, a) != _orientation(c, d, b)


def polygon_self_intersects(points: list[Point]) -> bool:
    size = len(points)
    for i in range(size):
        a, b = points[i], points[(i + 1) % size]
        for j in range(i + 1, size):
            if abs(i - j) <= 1 or (i == 0 and j == size - 1):
                continue
            c, d = points[j], points[(j + 1) % size]
            if segments_intersect(a, b, c, d):
                return True
    return False


def normalized_to_pixel(points: Iterable[Point], width: int, height: int) -> list[Point]:
    return [(x * width, y * height) for x, y in points]


def screen_to_normalized(
    point: Point, widget_size: Point, image_size: Point, fit: str = "contain"
) -> Point | None:
    if fit != "contain":
        raise ValueError("only BoxFit.contain mapping is supported")
    ww, wh = widget_size
    iw, ih = image_size
    scale = min(ww / iw, wh / ih)
    shown_w, shown_h = iw * scale, ih * scale
    left, top = (ww - shown_w) / 2, (wh - shown_h) / 2
    x, y = point
    if not (left <= x <= left + shown_w and top <= y <= top + shown_h):
        return None
    return ((x - left) / shown_w, (y - top) / shown_h)

