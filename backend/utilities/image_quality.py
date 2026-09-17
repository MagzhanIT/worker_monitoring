from __future__ import annotations


def image_quality(image) -> float:
    """Return a conservative [0,1] sharpness/brightness score for an ndarray."""
    if image is None or getattr(image, "size", 0) == 0:
        return 0.0
    try:
        import cv2
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        brightness = min(1.0, max(0.0, float(gray.mean()) / 128.0))
        sharpness = min(1.0, float(cv2.Laplacian(gray, cv2.CV_64F).var()) / 500.0)
        return round(0.4 * brightness + 0.6 * sharpness, 4)
    except Exception:
        return 0.0

