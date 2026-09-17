from __future__ import annotations

from dataclasses import dataclass

from config import settings
from services.phone_detector import PhoneCandidate
from utilities.geometry import bbox_area, center, distance


@dataclass
class PhoneAssociation:
    track_id: int | None
    candidate: PhoneCandidate
    phone_near_left_wrist: bool
    phone_near_right_wrist: bool
    phone_in_upper_body: bool
    phone_near_face: bool
    normalized_wrist_distance: float | None
    association_score: float
    association_status: str
    rejection_reason: str | None = None


def associate_phones(candidates: list[PhoneCandidate], people: list[dict]) -> list[PhoneAssociation]:
    """Greedy one-phone-to-one-person assignment with auditable diagnostics."""
    proposed: list[tuple[float, int, int, PhoneAssociation]] = []
    rejected: list[PhoneAssociation] = []
    for candidate_index, candidate in enumerate(candidates):
        phone_center = center(candidate.bbox)
        for person_index, person in enumerate(people):
            track_id, box = person["track_id"], person["bbox"]
            width, height = max(1, box[2] - box[0]), max(1, box[3] - box[1])
            inside = box[0] - 0.1 * width <= phone_center[0] <= box[2] + 0.1 * width and box[1] <= phone_center[1] <= box[3]
            area_ratio = bbox_area(candidate.bbox) / max(1, bbox_area(box))
            wrists = person.get("wrists", {})
            left = wrists.get("left")
            right = wrists.get("right")
            left_distance = distance(phone_center, left) / height if left else None
            right_distance = distance(phone_center, right) / height if right else None
            near_left = left_distance is not None and left_distance <= settings.phone_near_hand_distance_ratio
            near_right = right_distance is not None and right_distance <= settings.phone_near_hand_distance_ratio
            wrist_distance = min([value for value in (left_distance, right_distance) if value is not None], default=None)
            upper = phone_center[1] <= box[1] + 0.68 * height
            face = person.get("face")
            near_face = bool(face and distance(phone_center, face) / height <= settings.phone_near_head_distance_ratio)
            crop_origin = candidate.source_region in {"person", "upper_body", "left_wrist", "right_wrist"}

            if candidate.behavior:
                intersection = _intersection_area(candidate.bbox, box)
                smaller = min(bbox_area(candidate.bbox), bbox_area(box))
                overlaps_person = intersection / smaller >= 0.35 if smaller else False
                hand_near_face = bool(
                    face
                    and any(
                        distance(wrist, face) / height
                        <= settings.phone_behavior_max_hand_to_face_distance
                        for wrist in wrists.values()
                    )
                )
                if not overlaps_person or not (
                    hand_near_face
                    or (
                        not wrists
                        and candidate.confidence >= settings.phone_behavior_fallback_confidence
                    )
                ):
                    continue
                score = 0.55 + 0.30 * hand_near_face + 0.15 * crop_origin
            elif candidate.physical:
                minimum_confidence = (
                    settings.phone_wrist_candidate_confidence
                    if candidate.source_region in {"left_wrist", "right_wrist"}
                    else settings.phone_person_candidate_confidence
                )
                if (
                    candidate.confidence < minimum_confidence
                    or not inside
                    or not 0.0005 <= area_ratio <= 0.25
                ):
                    continue
                has_pose_geometry = bool(wrists or face)
                if has_pose_geometry and not (near_left or near_right or near_face):
                    continue
                if not has_pose_geometry and not (
                    upper
                    and candidate.confidence >= settings.phone_no_pose_fallback_confidence
                ):
                    continue
                score = 0.30 * inside + 0.20 * crop_origin + 0.30 * (near_left or near_right) + 0.10 * upper + 0.10 * near_face
            else:
                continue

            association = PhoneAssociation(track_id, candidate, near_left, near_right, upper, near_face, wrist_distance, round(score, 3), "ASSOCIATED" if score >= 0.5 else "WEAK")
            proposed.append((score, candidate_index, person_index, association))
    assigned_candidates: set[int] = set()
    assigned_people: set[int] = set()
    output: list[PhoneAssociation] = []
    for _, candidate_index, person_index, association in sorted(proposed, reverse=True, key=lambda item: item[0]):
        if candidate_index in assigned_candidates or person_index in assigned_people:
            continue
        if association.association_score < 0.5:
            continue
        assigned_candidates.add(candidate_index)
        assigned_people.add(person_index)
        output.append(association)
    for index, candidate in enumerate(candidates):
        if index not in assigned_candidates:
            rejected.append(PhoneAssociation(None, candidate, False, False, False, False, None, 0, "REJECTED", "No unique safe worker association"))
    return output + rejected


def _intersection_area(first, second) -> float:
    return max(0.0, min(first[2], second[2]) - max(first[0], second[0])) * max(
        0.0, min(first[3], second[3]) - max(first[1], second[1])
    )
