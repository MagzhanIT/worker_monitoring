from __future__ import annotations

from dataclasses import dataclass

from config import settings
from services.model_registry import model_registry


@dataclass
class PersonObservation:
    bbox: tuple[float, float, float, float]
    confidence: float
    class_name: str
    source: str = "primary"


def _intersection_over_smaller(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    smaller = min(first_area, second_area)
    return intersection / smaller if smaller else 0.0


def _intersection_over_box(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    """Intersection divided by the second box (the expected coat box)."""
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    second_area = max(0.0, second[2] - second[0]) * max(
        0.0, second[3] - second[1]
    )
    return intersection / second_area if second_area else 0.0


def _suppress_duplicate_coats(
    coats: list[PersonObservation],
) -> list[PersonObservation]:
    output: list[PersonObservation] = []
    for candidate in sorted(
        coats,
        key=lambda item: (item.source != "verifier", item.confidence),
        reverse=True,
    ):
        if any(
            _intersection_over_smaller(candidate.bbox, existing.bbox) >= 0.70
            for existing in output
        ):
            continue
        output.append(candidate)
    return output


def merge_role_observations(observations: list[PersonObservation]) -> list[PersonObservation]:
    """Attach a coat box to its enclosing person instead of tracking it twice."""
    people = [item for item in observations if item.class_name == "person"]
    coats = _suppress_duplicate_coats(
        [item for item in observations if item.class_name == "lab_coat"]
    )
    unmatched_coats = set(range(len(coats)))
    merged: list[PersonObservation] = []
    for person in people:
        matches = [
            index
            for index in unmatched_coats
            if (
                person.bbox[0]
                <= (coats[index].bbox[0] + coats[index].bbox[2]) * 0.5
                <= person.bbox[2]
                and person.bbox[1]
                <= (coats[index].bbox[1] + coats[index].bbox[3]) * 0.5
                <= person.bbox[3]
                and _intersection_over_box(person.bbox, coats[index].bbox)
                >= settings.lab_coat_min_person_overlap
            )
        ]
        if matches:
            best = max(matches, key=lambda index: coats[index].confidence)
            unmatched_coats.difference_update(matches)
            merged.append(
                PersonObservation(
                    person.bbox,
                    max(person.confidence, coats[best].confidence),
                    "lab_coat",
                    person.source,
                )
            )
        else:
            merged.append(person)
    # The verifier detects clothing, not a complete person. An isolated
    # verifier coat must never become a separate person track. Primary-model
    # coat detections remain valid because that model was trained for the
    # project's worker/person boxes.
    merged.extend(
        coats[index]
        for index in sorted(unmatched_coats)
        if coats[index].source != "verifier"
    )
    merged.extend(item for item in observations if item.class_name not in {"person", "lab_coat"})
    return merged


def valid_tracking_observation(
    observation: PersonObservation, frame_width: int, frame_height: int
) -> bool:
    """Reject malformed and tiny boxes that create one-frame CCTV noise."""
    left, top, right, bottom = observation.bbox
    box_width = max(0.0, min(float(frame_width), right) - max(0.0, left))
    box_height = max(0.0, min(float(frame_height), bottom) - max(0.0, top))
    if box_width < 10 or box_height < settings.person_min_box_height_pixels:
        return False
    frame_area = max(1.0, float(frame_width * frame_height))
    return (box_width * box_height) / frame_area >= settings.person_min_box_area_ratio


class PersonDetector:
    def __init__(self) -> None:
        self.model = None
        self.lab_coat_verifier = None
        self.allowed: set[str] = set()
        self._frame_count = 0
        self.last_diagnostics: dict[str, int] = {}

    def load(self) -> bool:
        self.model = model_registry.load("person", settings.person_model_path, settings.person_confidence, 640)
        names = set(model_registry.metadata["person"].class_names)
        requested = {"person"} if settings.worker_detection_mode == "person" else {"lab_coat"} if settings.worker_detection_mode == "lab_coat" else {"person", "lab_coat"}
        self.allowed = names & requested
        if (
            settings.lab_coat_verifier_enabled
            and settings.worker_detection_mode != "person"
        ):
            self.lab_coat_verifier = model_registry.load(
                "lab_coat_verifier",
                settings.lab_coat_verifier_model_path,
                settings.lab_coat_verifier_confidence,
                640,
            )
        return bool(self.model and self.allowed)

    def detect(self, frame) -> list[PersonObservation]:
        if self.model is None:
            self.last_diagnostics = {}
            return []
        self._frame_count += 1
        result = model_registry.predict(
            "person",
            self.model,
            frame,
            conf=min(settings.person_confidence, settings.lab_coat_confidence),
            verbose=False,
        )[0]
        names = result.names
        observations = []
        primary_candidates = 0
        for box in result.boxes:
            class_name = names[int(box.cls.item())]
            if class_name in self.allowed:
                primary_candidates += 1
                observations.append(PersonObservation(tuple(float(v) for v in box.xyxy[0].tolist()), float(box.conf.item()), class_name))
        verifier_candidates = 0
        if (
            self.lab_coat_verifier is not None
            and self._frame_count % settings.lab_coat_verifier_every_n_frames == 0
        ):
            verifier_result = model_registry.predict(
                "lab_coat_verifier",
                self.lab_coat_verifier,
                frame,
                conf=settings.lab_coat_verifier_confidence,
                verbose=False,
            )[0]
            verifier_names = verifier_result.names
            for box in verifier_result.boxes:
                class_name = str(verifier_names[int(box.cls.item())]).lower().replace(
                    " ", "_"
                )
                if class_name == "lab_coat":
                    verifier_candidates += 1
                    observations.append(
                        PersonObservation(
                            tuple(float(value) for value in box.xyxy[0].tolist()),
                            float(box.conf.item()),
                            "lab_coat",
                            "verifier",
                        )
                    )
        height, width = frame.shape[:2]
        merged = merge_role_observations(observations)
        filtered = [
            observation
            for observation in merged
            if valid_tracking_observation(observation, width, height)
        ]
        self.last_diagnostics = {
            "primary_candidates": primary_candidates,
            "verifier_coat_candidates": verifier_candidates,
            "fusion_reduction": max(0, len(observations) - len(merged)),
            "geometry_rejected": max(0, len(merged) - len(filtered)),
            "tracking_detections": len(filtered),
        }
        return filtered
