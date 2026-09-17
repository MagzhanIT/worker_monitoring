from __future__ import annotations

from config import settings
from services.pose_service import COCO_BONES


class DebugOverlayRenderer:
    """Draw developer evidence on a copy; the clean inference frame is immutable input."""

    @staticmethod
    def render(clean_frame, context: dict, options: dict):
        import cv2

        output = clean_frame.copy()
        height, width = output.shape[:2]
        if options.get("show_zones", True):
            palette = {
                "waiting": (190, 80, 230),
                "customer_area": (180, 100, 220),
                "service_position": (40, 210, 130),
                "cashier": (40, 210, 130),
                "shelf_interaction": (30, 170, 250),
                "medicine": (30, 170, 250),
                "register_interaction": (255, 190, 30),
            }
            for zone in context.get("zones", []):
                points = [
                    (int(point[0] * width), int(point[1] * height))
                    for point in zone.get("normalized_points", [])
                ]
                if len(points) < 3:
                    continue
                import numpy as np

                polygon = np.asarray(points, dtype=np.int32)
                color = palette.get(zone.get("zone_type"), (180, 180, 80))
                cv2.polylines(output, [polygon], True, color, 2)
                cv2.putText(
                    output,
                    zone.get("zone_type", "zone"),
                    points[0],
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.48,
                    color,
                    1,
                    cv2.LINE_AA,
                )

        people_by_track = {}
        for person in context.get("people", []):
            bbox = person.get("bbox")
            if not bbox:
                continue
            left, top, right, bottom = [int(value) for value in bbox]
            role = person.get("role", "UNKNOWN")
            color = (40, 210, 120) if role == "WORKER" else (210, 120, 230) if role == "CUSTOMER" else (160, 160, 160)
            cv2.rectangle(output, (left, top), (right, bottom), color, 2)
            identifier = person.get("worker_session_id") or person.get("customer_session_id") or f"C{context.get('camera_id')}-{role[:1]}-{person.get('track_id')}"
            activity = person.get("activity") or person.get("customer_phase") or "UNKNOWN"
            label = f"{identifier} | T{person.get('track_id')} | {activity} | {float(person.get('confidence', 0)):.2f}"
            if person.get("global_worker_id"):
                label += f" | {person['global_worker_id']}"
            if person.get("identity_match_status"):
                label += f" | ID:{person['identity_match_status']}"
            if person.get("tracker_predicted"):
                label += (
                    f" | tracker grace "
                    f"{float(person.get('tracker_grace_remaining', 0)):.1f}s"
                )
            stitch = person.get("session_stitch") or {}
            if stitch:
                label += (
                    f" | STITCH T{stitch.get('previous_track_id')} "
                    f"{float(stitch.get('confidence', 0)):.2f}"
                )
            if person.get("customer_session_id"):
                label += (
                    f" | wait {float(person.get('waiting_seconds', 0)):.1f}s"
                    f" service {float(person.get('service_seconds', 0)):.1f}s"
                )
            phone = person.get("phone_evidence") or {}
            if phone:
                label += (
                    f" | phone obj {float(phone.get('physical_phone_object_confidence', 0)):.2f}"
                    f" fused {float(phone.get('final_fused_phone_confidence', 0)):.2f}"
                )
            unknown = person.get("unknown_reason")
            if unknown:
                label += f" | unknown:{unknown}"
            detail_lines = [label]
            if role == "WORKER":
                detail_lines.extend(
                    [
                        (
                            f"candidate={person.get('candidate_activity') or 'none'} "
                            f"{float(person.get('candidate_duration_seconds', 0)):.1f}s | "
                            f"idle={float(person.get('idle_candidate_seconds', 0)):.1f}/"
                            f"{float(person.get('idle_confirmation_seconds', 0)):.1f}s | "
                            f"confirmed={float(person.get('confirmed_idle_seconds', 0)):.1f}s"
                        ),
                        (
                            f"track age={float(person.get('track_age_seconds', 0)):.1f}s "
                            f"stable={bool(person.get('track_stable'))} | "
                            f"quality={person.get('evidence_quality', 'LOW')}"
                        ),
                        (
                            f"motion body={float(person.get('body_motion', 0)):.3f} "
                            f"bbox={float(person.get('bbox_motion', 0)):.3f} "
                            f"wrist={float(person.get('wrist_motion', 0)):.3f} "
                            f"elbow={float(person.get('elbow_motion', 0)):.3f}"
                        ),
                        (
                            f"pose={person.get('pose_status', 'MISSING')} "
                            f"{float(person.get('pose_confidence', 0)):.2f} | "
                            f"zone={person.get('zone') or 'none'} | "
                            f"service={person.get('customer_service_phase') or 'none'}"
                        ),
                    ]
                )
                blockers = person.get("idle_blocking_reasons") or []
                if blockers:
                    detail_lines.append("idle blocked: " + "; ".join(blockers[:3]))
            elif role == "CUSTOMER" and person.get("customer_session_id"):
                detail_lines.extend(
                    [
                        (
                            f"waiting={float(person.get('waiting_seconds', 0)):.1f}s | "
                            f"service={float(person.get('service_seconds', 0)):.1f}s | "
                            f"retrieval={float(person.get('medicine_retrieval_seconds', 0)):.1f}s"
                        ),
                        (
                            f"assigned={person.get('assigned_worker_session_id') or 'none'} | "
                            f"confidence={float(person.get('assignment_confidence', 0)):.2f} | "
                            f"phase={person.get('customer_phase', 'WAITING')}"
                        ),
                    ]
                )
            _draw_lines(
                output,
                detail_lines,
                left,
                max(18, top - 7),
                color,
            )
            people_by_track[person.get("track_id")] = person

        if options.get("show_pose", True):
            for track_id, points in context.get("poses", {}).items():
                for first, second in COCO_BONES:
                    if first >= len(points) or second >= len(points):
                        continue
                    a, b = points[first], points[second]
                    if (
                        a[2] >= settings.pose_keypoint_confidence
                        and b[2] >= settings.pose_keypoint_confidence
                    ):
                        cv2.line(output, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), (255, 220, 40), 2)
                for x, y, confidence in points:
                    if confidence >= settings.pose_keypoint_confidence:
                        cv2.circle(output, (int(x), int(y)), 3, (255, 220, 40), -1)

        if options.get("show_phone_boxes", True):
            for item in context.get("phone_candidates", []):
                box = item.get("bbox")
                if not box:
                    continue
                left, top, right, bottom = [int(value) for value in box]
                confirmed = item.get("associated", False)
                color = (20, 30, 240) if confirmed else (30, 170, 250)
                cv2.rectangle(output, (left, top), (right, bottom), color, 2)
                cv2.putText(
                    output,
                    f"phone {float(item.get('confidence', 0)):.3f} {item.get('source_region', '')}",
                    (left, max(18, top - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.42,
                    color,
                    1,
                    cv2.LINE_AA,
                )

        if options.get("show_assignments", True):
            for assignment in context.get("assignments", []):
                worker = people_by_track.get(assignment.get("worker_track_id"))
                customer = people_by_track.get(assignment.get("customer_track_id"))
                if not worker or not customer:
                    continue
                worker_center = _center(worker["bbox"])
                customer_center = _center(customer["bbox"])
                cv2.line(output, worker_center, customer_center, (255, 255, 255), 2)
                midpoint = ((worker_center[0] + customer_center[0]) // 2, (worker_center[1] + customer_center[1]) // 2)
                cv2.putText(
                    output,
                    f"{assignment.get('service_session_id')} {assignment.get('phase')}",
                    midpoint,
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.42,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )

        if options.get("show_performance", True):
            stats = context.get("performance", {})
            lines = [
                "TEST MODE - AI EVIDENCE",
                f"Camera {context.get('camera_id')} | frame {context.get('frame_number', 0)}",
                f"Capture {stats.get('capture_fps', 0):.1f} FPS | Processing {stats.get('processing_fps', 0):.1f} FPS",
                f"People {stats.get('people', 0)} | Workers {stats.get('workers', 0)} | Customers {stats.get('customers', 0)}",
                f"Candidates {stats.get('candidates', 0)} | Person {stats.get('person_ms', 0):.1f} ms | Tracker {stats.get('tracker_ms', 0):.1f} ms",
                f"Pose {stats.get('pose_ms', 0):.1f} ms | Phone crops {stats.get('phone_ms', 0):.1f} ms | Total {stats.get('total_ms', 0):.1f} ms",
                f"Services {stats.get('active_services', 0)} | Waiting {stats.get('waiting_customers', 0)}",
                f"Phone model {stats.get('phone_mode', 'unavailable')}",
            ]
            panel_width = min(width - 16, 520)
            panel_height = 24 + len(lines) * 23
            overlay = output.copy()
            cv2.rectangle(overlay, (8, 8), (8 + panel_width, 8 + panel_height), (10, 20, 18), -1)
            cv2.addWeighted(overlay, 0.78, output, 0.22, 0, output)
            for index, line in enumerate(lines):
                cv2.putText(
                    output,
                    line,
                    (18, 33 + index * 23),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.52,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
        return output


def _center(box) -> tuple[int, int]:
    return int((box[0] + box[2]) / 2), int((box[1] + box[3]) / 2)


def _draw_lines(frame, lines: list[str], x: int, y: int, color) -> None:
    """Draw bounded TEST diagnostics; this is never called on inference input."""
    import cv2

    height, width = frame.shape[:2]
    start_x = max(2, min(width - 4, x))
    start_y = max(15, y)
    for index, value in enumerate(lines[:6]):
        text = str(value)[:150]
        row_y = min(height - 4, start_y + index * 15)
        cv2.putText(
            frame,
            text,
            (start_x, row_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            color,
            1,
            cv2.LINE_AA,
        )
