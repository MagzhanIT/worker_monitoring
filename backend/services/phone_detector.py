from __future__ import annotations

from dataclasses import dataclass
import json
import time

from config import settings
from services.model_registry import model_registry

PHYSICAL_NAMES = {"phone", "cell phone", "mobile phone", "smartphone"}
BEHAVIOUR_NAMES = {"phone_call"}


def inspect_phone_classes(class_names: list[str]) -> str:
    names = {name.lower().strip() for name in class_names}
    physical = bool(names & PHYSICAL_NAMES)
    behavior = bool(names & BEHAVIOUR_NAMES)
    if physical and behavior:
        return "MIXED_PHONE_MODEL"
    if physical:
        return "PHYSICAL_PHONE_MODEL"
    if behavior:
        return "PHONE_BEHAVIOUR_MODEL"
    return "INVALID_PHONE_MODEL"


@dataclass
class PhoneCandidate:
    bbox: tuple[float, float, float, float]
    confidence: float
    class_name: str
    source_region: str

    @property
    def physical(self) -> bool:
        return self.class_name.lower().strip() in PHYSICAL_NAMES

    @property
    def behavior(self) -> bool:
        return self.class_name.lower().strip() in BEHAVIOUR_NAMES


class PhoneDetector:
    def __init__(self) -> None:
        self.model = None
        self.mode = "INVALID_PHONE_MODEL"
        self.class_ids: list[int] = []
        self._last_debug_save: dict[int, float] = {}

    def load(self) -> bool:
        self.model = model_registry.load("phone", settings.phone_model_path, settings.phone_object_confidence, settings.phone_person_crop_imgsz)
        class_names = model_registry.metadata["phone"].class_names
        self.mode = inspect_phone_classes(class_names)
        allowed_names = PHYSICAL_NAMES | BEHAVIOUR_NAMES
        self.class_ids = [
            index
            for index, name in enumerate(class_names)
            if name.lower().strip() in allowed_names
        ]
        return bool(self.model and self.mode != "INVALID_PHONE_MODEL" and self.class_ids)

    @staticmethod
    def crop_to_frame(box, crop_box, crop_size, inference_size):
        left, top, right, bottom = crop_box
        shown_w, shown_h = crop_size
        scale_x, scale_y = shown_w / inference_size[0], shown_h / inference_size[1]
        x1, y1, x2, y2 = box
        return left + x1 * scale_x, top + y1 * scale_y, left + x2 * scale_x, top + y2 * scale_y

    def detect_crop(self, crop, crop_box, source_region="person") -> list[PhoneCandidate]:
        if self.model is None:
            return []
        image_size = (
            settings.phone_wrist_crop_imgsz
            if source_region in {"left_wrist", "right_wrist"}
            else settings.phone_person_crop_imgsz
        )
        result = model_registry.predict(
            "phone",
            self.model,
            crop,
            classes=self.class_ids,
            imgsz=image_size,
            conf=settings.phone_object_confidence,
            verbose=False,
        )[0]
        output = []
        for box in result.boxes:
            name = result.names[int(box.cls.item())]
            xyxy = tuple(float(v) for v in box.xyxy[0].tolist())
            # Ultralytics xyxy is already in input image coordinates after preprocessing.
            global_box = (crop_box[0] + xyxy[0], crop_box[1] + xyxy[1], crop_box[0] + xyxy[2], crop_box[1] + xyxy[3])
            output.append(PhoneCandidate(global_box, float(box.conf.item()), name, source_region))
        return output

    def save_debug_miss(self, track_id: int, images: dict[str, object], metadata: dict, cooldown_seconds: float = 30.0) -> str | None:
        """Best-effort local diagnostics; failures never interrupt monitoring."""
        now = time.monotonic()
        if now - self._last_debug_save.get(track_id, -cooldown_seconds) < cooldown_seconds:
            return None
        try:
            import cv2
            from config import BACKEND_DIR
            folder = BACKEND_DIR / "debug_phone_misses" / f"track_{track_id}_{int(time.time())}"
            folder.mkdir(parents=True, exist_ok=True)
            for name, image in images.items():
                if image is not None and getattr(image, "size", 0):
                    cv2.imwrite(str(folder / f"{name}.jpg"), image)
            (folder / "metadata.json").write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
            self._last_debug_save[track_id] = now
            return str(folder)
        except Exception:
            return None


class PhoneSearchScheduler:
    def __init__(self) -> None:
        self.focused_until: dict[int, float] = {}
        self._seen_regions: set[tuple[int, int, str]] = set()

    def begin_frame(self) -> None:
        self._seen_regions.clear()

    def trigger_focused(self, track_id: int, now: float) -> None:
        self.focused_until[track_id] = max(self.focused_until.get(track_id, 0), now + settings.phone_focused_search_seconds)

    def is_focused(self, track_id: int, now: float) -> bool:
        return self.focused_until.get(track_id, 0) >= now

    def should_search(self, track_id: int, frame_sequence: int, region: str, now: float) -> bool:
        key = (track_id, frame_sequence, region)
        if key in self._seen_regions:
            return False
        focused = self.focused_until.get(track_id, 0) >= now
        interval = settings.phone_focused_run_every_n_frames if focused else settings.phone_run_every_n_frames
        if frame_sequence % interval:
            return False
        self._seen_regions.add(key)
        return True

    def clear(self, track_id: int) -> None:
        self.focused_until.pop(track_id, None)
