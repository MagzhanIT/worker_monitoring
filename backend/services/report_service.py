from __future__ import annotations

import csv
import html
import os
import statistics
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import BACKEND_DIR, settings
from db_models.activity_event import ActivityEvent
from db_models.customer_session import CustomerSession
from db_models.customer_service import WorkerSessionStitch
from db_models.worker_identity import WorkerIdentity, WorkerIdentityLink
from db_models.worker_session import WorkerSession
from db_models.worker_snapshot import WorkerSnapshot
from services.sheets_service import upload_aggregates
from services.customer_analytics import (
    customer_metrics,
    customer_trust_classification,
)
from services.evidence_service import normalize_unknown_reason
from utilities.time_utils import day_bounds, ensure_utc, seconds_between

REPORT_DIR = BACKEND_DIR / "reports"

ACTIVITY_FIELDS = {
    "SERVING_CUSTOMER": "serving_customer_seconds",
    "FETCHING_MEDICINE": "fetching_medicine_seconds",
    "CASHIER_WORK": "cashier_work_seconds",
    "COMPUTER_POS_WORK": "computer_pos_seconds",
    "SHELF_WORK": "shelf_work_seconds",
    "OTHER_WORK": "other_work_seconds",
    "APPROVED_BREAK": "approved_break_seconds",
    "ON_PHONE": "confirmed_phone_seconds",
    "POSSIBLE_PHONE": "possible_phone_seconds",
    "POSSIBLE_IDLE": "possible_idle_seconds",
    "IDLE": "confirmed_idle_seconds",
    "UNKNOWN": "unknown_activity_seconds",
}
ACTIVITY_LABELS = {
    "SERVING_CUSTOMER": "Serving customer",
    "FETCHING_MEDICINE": "Fetching medicine for active customer service",
    "CASHIER_WORK": "Cashier work",
    "COMPUTER_POS_WORK": "Computer/POS work",
    "SHELF_WORK": "Shelf work",
    "OTHER_WORK": "Other observed work",
    "APPROVED_BREAK": "Approved break",
    "ON_PHONE": "Confirmed physical-phone evidence",
    "POSSIBLE_PHONE": "Possible phone evidence - review needed",
    "POSSIBLE_IDLE": "Possible inactivity - review needed",
    "IDLE": "Confirmed idle",
    "UNKNOWN": "Unknown - insufficient evidence",
}
PRODUCTIVE_ACTIVITIES = {
    "SERVING_CUSTOMER",
    "FETCHING_MEDICINE",
    "CASHIER_WORK",
    "COMPUTER_POS_WORK",
    "SHELF_WORK",
    "OTHER_WORK",
}

WORKER_HEADERS = [
    "report_date",
    "worker_label",
    "global_worker_id",
    "identity_status",
    "identity_confidence",
    "identity_method",
    "session_count",
    "camera_ids",
    "worker_session_ids",
    "worker_session_id",
    "employee_ids",
    "employee_id",
    "camera_id",
    "first_seen",
    "last_seen",
    "observed_time",
    "observed_seconds",
    "confirmed_work_time",
    "confirmed_work_seconds",
    "serving_customer_seconds",
    "fetching_medicine_seconds",
    "cashier_work_seconds",
    "computer_pos_seconds",
    "shelf_work_seconds",
    "other_work_seconds",
    "approved_break_seconds",
    "confirmed_phone_seconds",
    "possible_phone_seconds",
    "possible_idle_seconds",
    "confirmed_idle_time",
    "confirmed_idle_seconds",
    "idle_event_count",
    "average_idle_interval_seconds",
    "median_idle_interval_seconds",
    "longest_idle_interval_seconds",
    "unknown_activity_seconds",
    "dominant_unknown_reason",
    "classification_coverage_percent",
    "reliable_work_percentage",
    "customers_served",
    "medicine_retrieval_seconds",
    "quality_status",
    "out_of_zone_seconds",
    "absent_seconds",
    "face_capture_path",
    "body_capture_path",
]
EVENT_HEADERS = [
    "event_id",
    "worker_label",
    "global_worker_id",
    "identity_status",
    "worker_session_id",
    "camera_id",
    "presence",
    "activity",
    "activity_label",
    "start_time",
    "end_time",
    "duration_seconds",
    "confidence",
    "review_status",
    "unknown_reason",
    "physical_phone_object_confidence",
    "pose_support_confidence",
    "context_support_confidence",
    "temporal_phone_confidence",
    "final_fused_phone_confidence",
    "raw_track_ids",
    "confirmation_seconds",
    "evidence_quality",
    "average_body_movement",
    "average_wrist_movement",
    "average_elbow_movement",
    "ending_reason",
    "transition_type",
    "end_transition_type",
]
CUSTOMER_HEADERS = [
    "customer_session_id",
    "camera_id",
    "customer_track_ids",
    "arrival_time",
    "waiting_started_at",
    "waiting_duration",
    "waiting_seconds",
    "service_started_at",
    "service_completed_at",
    "total_service_duration",
    "service_seconds",
    "direct_interaction_duration",
    "direct_interaction_seconds",
    "medicine_retrieval_duration",
    "medicine_retrieval_seconds",
    "transaction_duration",
    "transaction_seconds",
    "assigned_worker_session_id",
    "current_service_phase",
    "outcome",
    "review_status",
    "trust_classification",
    "assignment_confidence",
]
REPORT_PATTERNS = (
    "latest_report*.csv",
    "latest_events*.csv",
    "latest_customer_report*.csv",
    "latest_manager_report*.html",
)


def _csv(path: Path, rows: list[dict], headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _duration_text(seconds: float | int | None) -> str:
    total = max(0, round(float(seconds or 0)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _display_datetime(value: datetime | None) -> str:
    """Use a manager-readable timestamp while retaining ISO values in CSV files."""
    return ensure_utc(value).strftime("%Y-%m-%d %H:%M:%S UTC") if value else ""


def _event_duration(event: ActivityEvent) -> float:
    if event.duration_seconds is not None:
        return max(0.0, float(event.duration_seconds))
    return seconds_between(event.start_time, event.end_time) or 0.0


def _union_seconds(intervals: list[tuple[datetime, datetime]]) -> float:
    normalized = sorted(
        (ensure_utc(start), ensure_utc(end))
        for start, end in intervals
        if start is not None and end is not None and ensure_utc(end) >= ensure_utc(start)
    )
    if not normalized:
        return 0.0
    total = 0.0
    current_start, current_end = normalized[0]
    for start, end in normalized[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            total += (current_end - current_start).total_seconds()
            current_start, current_end = start, end
    return max(0.0, total + (current_end - current_start).total_seconds())


def _event_union(events: list[ActivityEvent]) -> float:
    intervals = [
        (event.start_time, event.end_time)
        for event in events
        if event.end_time is not None
    ]
    if intervals:
        return _union_seconds(intervals)
    return sum(_event_duration(event) for event in events)


def _activity_totals(events: list[ActivityEvent]) -> dict[str, float]:
    accepted = [event for event in events if event.review_status != "false_alarm"]
    totals: defaultdict[str, float] = defaultdict(float)
    for activity, field in ACTIVITY_FIELDS.items():
        totals[field] = _event_union(
            [event for event in accepted if event.activity == activity]
        )
    totals["confirmed_work_seconds"] = _event_union(
        [event for event in accepted if event.activity in PRODUCTIVE_ACTIVITIES]
    )
    totals["out_of_zone_seconds"] = _event_union(
        [event for event in accepted if event.presence == "OUT_OF_ZONE"]
    )
    totals["absent_seconds"] = _event_union(
        [event for event in accepted if event.presence == "ABSENT"]
    )
    return totals


def _snapshot_url(snapshot: WorkerSnapshot) -> str:
    relative_path = snapshot.file_path.replace("\\", "/")
    return f"../worker_snapshots/{quote(relative_path, safe='/')}"


def _remove_obsolete_exports(current_paths: set[Path]) -> None:
    """Remove generated report exports only; raw events and snapshots are untouched."""
    for pattern in REPORT_PATTERNS:
        for path in REPORT_DIR.glob(pattern):
            if path.is_file() and path not in current_paths:
                path.unlink()


def _identity_summary(
    identity: WorkerIdentity | None,
    links: list[WorkerIdentityLink],
) -> tuple[str, str, float | str, str]:
    if identity is None:
        return "", "not_linked", "", "none"
    if any(link.match_status == "manager_confirmed" for link in links):
        status = "manager_confirmed"
    elif any(link.match_status == "ambiguous_separate" for link in links):
        status = "review_required"
    elif any(link.match_status == "appearance_matched" for link in links):
        status = "appearance_matched"
    else:
        status = identity.status
    confidence = min((float(link.confidence or 0) for link in links), default=0.0)
    methods = ", ".join(sorted({link.match_method for link in links}))
    return identity.id, status, round(confidence, 3), methods


def _customer_row(session: CustomerSession) -> dict:
    outcome = (
        "COMPLETED"
        if session.completed and session.outcome == "ACTIVE"
        else "ABANDONED"
        if session.left_without_service and session.outcome == "ACTIVE"
        else session.outcome
    )
    trust_classification = customer_trust_classification(session)
    return {
        "customer_session_id": session.id,
        "camera_id": session.camera_id,
        "customer_track_ids": ",".join(
            str(value)
            for value in (session.original_track_ids_json or [session.customer_track_id])
        ),
        "arrival_time": session.waiting_started_at.isoformat(),
        "arrival_display": _display_datetime(session.waiting_started_at),
        "waiting_started_at": session.waiting_started_at.isoformat(),
        "waiting_duration": _duration_text(session.waiting_seconds),
        "waiting_seconds": round(float(session.waiting_seconds or 0), 3),
        "service_started_at": (
            session.service_started_at.isoformat() if session.service_started_at else ""
        ),
        "service_started_display": _display_datetime(session.service_started_at),
        "service_completed_at": (
            session.service_completed_at.isoformat()
            if session.service_completed_at
            else ""
        ),
        "total_service_duration": _duration_text(session.service_seconds),
        "service_seconds": round(float(session.service_seconds or 0), 3),
        "direct_interaction_duration": _duration_text(
            session.direct_interaction_seconds
        ),
        "direct_interaction_seconds": round(
            float(session.direct_interaction_seconds or 0), 3
        ),
        "medicine_retrieval_duration": _duration_text(
            session.medicine_retrieval_seconds
        ),
        "medicine_retrieval_seconds": round(
            float(session.medicine_retrieval_seconds or 0), 3
        ),
        "transaction_duration": _duration_text(session.transaction_seconds),
        "transaction_seconds": round(float(session.transaction_seconds or 0), 3),
        "assigned_worker_session_id": session.worker_session_id or "",
        "current_service_phase": session.current_phase,
        "outcome": outcome,
        "review_status": session.review_status,
        "trust_classification": trust_classification,
        "assignment_confidence": round(float(session.assignment_confidence or 0), 3),
    }


def _group_row(report_date: date, group: dict) -> dict:
    sessions: list[WorkerSession] = group["sessions"]
    events: list[ActivityEvent] = group["events"]
    snapshots: list[WorkerSnapshot] = group["snapshots"]
    identity: WorkerIdentity | None = group["identity"]
    links: list[WorkerIdentityLink] = group["links"]
    customer_sessions: list[CustomerSession] = group.get("customer_sessions", [])
    totals = _activity_totals(events)
    accepted_events = [event for event in events if event.review_status != "false_alarm"]
    idle_events = [event for event in accepted_events if event.activity == "IDLE"]
    idle_durations = [_event_duration(event) for event in idle_events]
    unknown_reasons: defaultdict[str, float] = defaultdict(float)
    for event in accepted_events:
        if event.activity == "UNKNOWN":
            unknown_reasons[
                normalize_unknown_reason(
                    "UNKNOWN", event.unknown_reason, legacy=True
                )
            ] += _event_duration(event)
    dominant_unknown_reason = (
        max(unknown_reasons, key=unknown_reasons.get) if unknown_reasons else ""
    )
    reliable_seconds = (
        totals["confirmed_work_seconds"]
        + totals["confirmed_idle_seconds"]
        + totals["confirmed_phone_seconds"]
    )
    review_seconds = (
        totals["unknown_activity_seconds"]
        + totals["possible_phone_seconds"]
        + totals["possible_idle_seconds"]
    )
    observed_seconds = _union_seconds(
        [(session.first_seen, session.last_seen) for session in sessions]
    )
    if not observed_seconds:
        observed_seconds = max(
            (float(session.observed_seconds or 0) for session in sessions), default=0.0
        )
    first_seen = min(ensure_utc(session.first_seen) for session in sessions)
    last_seen = max(ensure_utc(session.last_seen) for session in sessions)
    camera_ids = sorted({session.camera_id for session in sessions})
    session_ids = [session.id for session in sessions]
    employee_ids = sorted(
        {session.employee_id for session in sessions if session.employee_id is not None}
    )
    media: dict[str, WorkerSnapshot] = {}
    for snapshot in sorted(snapshots, key=lambda item: item.quality, reverse=True):
        media.setdefault(snapshot.kind, snapshot)
    global_id, identity_status, identity_confidence, identity_method = _identity_summary(
        identity, links
    )
    worker_label = (
        identity.display_name
        if identity is not None
        else f"Unlinked worker session {sessions[0].id}"
    )
    row = {
        "report_date": report_date.isoformat(),
        "worker_label": worker_label,
        "global_worker_id": global_id,
        "identity_status": identity_status,
        "identity_confidence": identity_confidence,
        "identity_method": identity_method,
        "session_count": len(sessions),
        "camera_ids": ",".join(str(value) for value in camera_ids),
        "worker_session_ids": ",".join(session_ids),
        "worker_session_id": session_ids[0] if len(session_ids) == 1 else ",".join(session_ids),
        "employee_ids": ",".join(str(value) for value in employee_ids),
        "employee_id": employee_ids[0] if len(employee_ids) == 1 else "",
        "camera_id": camera_ids[0] if len(camera_ids) == 1 else ",".join(str(value) for value in camera_ids),
        "first_seen": first_seen.isoformat(),
        "last_seen": last_seen.isoformat(),
        "observed_time": _duration_text(observed_seconds),
        "observed_seconds": round(observed_seconds, 3),
        "confirmed_work_time": _duration_text(totals["confirmed_work_seconds"]),
        "confirmed_idle_time": _duration_text(totals["confirmed_idle_seconds"]),
        "idle_event_count": len(idle_events),
        "average_idle_interval_seconds": round(
            statistics.fmean(idle_durations), 3
        ) if idle_durations else 0.0,
        "median_idle_interval_seconds": round(
            statistics.median(idle_durations), 3
        ) if idle_durations else 0.0,
        "longest_idle_interval_seconds": round(max(idle_durations), 3)
        if idle_durations
        else 0.0,
        "dominant_unknown_reason": dominant_unknown_reason,
        "classification_coverage_percent": round(
            100 * reliable_seconds / (reliable_seconds + review_seconds), 2
        ) if reliable_seconds + review_seconds else 0.0,
        "reliable_work_percentage": round(
            100 * totals["confirmed_work_seconds"] / reliable_seconds, 2
        ) if reliable_seconds else 0.0,
        "customers_served": sum(
            item.outcome == "COMPLETED" for item in customer_sessions
        ),
        "medicine_retrieval_seconds": round(
            sum(float(item.medicine_retrieval_seconds or 0) for item in customer_sessions),
            3,
        ),
        "quality_status": (
            "review_required"
            if identity_status in {"review_required", "appearance_matched"}
            else identity_status
        ),
        "face_capture_path": media["face"].file_path if "face" in media else "",
        "body_capture_path": media["body"].file_path if "body" in media else "",
    }
    for field in WORKER_HEADERS:
        if field.endswith("_seconds") and field not in row:
            row[field] = round(totals[field], 3)
    group["media"] = media
    group["worker_label"] = worker_label
    return row


def _event_row(
    event: ActivityEvent,
    session: WorkerSession,
    identity: WorkerIdentity | None,
    link: WorkerIdentityLink | None,
) -> dict:
    evidence = event.evidence_json or {}
    return {
        "event_id": event.id,
        "worker_label": identity.display_name if identity else session.display_name,
        "global_worker_id": identity.id if identity else "",
        "identity_status": link.match_status if link else "not_linked",
        "worker_session_id": event.worker_session_id,
        "camera_id": event.camera_id,
        "presence": event.presence,
        "activity": event.activity,
        "activity_label": ACTIVITY_LABELS.get(
            event.activity, event.activity.replace("_", " ").title()
        ),
        "start_time": event.start_time.isoformat(),
        "end_time": event.end_time.isoformat() if event.end_time else "",
        "duration_seconds": round(_event_duration(event), 3),
        "confidence": event.confidence,
        "review_status": event.review_status,
        "unknown_reason": normalize_unknown_reason(
            event.activity, event.unknown_reason, legacy=True
        ) or "",
        "physical_phone_object_confidence": evidence.get(
            "physical_phone_object_confidence", ""
        ),
        "pose_support_confidence": evidence.get("pose_support_confidence", ""),
        "context_support_confidence": evidence.get(
            "context_support_confidence", ""
        ),
        "temporal_phone_confidence": evidence.get(
            "temporal_phone_confidence", ""
        ),
        "final_fused_phone_confidence": evidence.get(
            "final_fused_phone_confidence", ""
        ),
        "raw_track_ids": ",".join(
            str(value) for value in (event.raw_track_ids_json or [event.track_id])
        ),
        "confirmation_seconds": event.confirmation_seconds or "",
        "evidence_quality": event.evidence_quality or "",
        "average_body_movement": event.average_body_movement or "",
        "average_wrist_movement": event.average_wrist_movement or "",
        "average_elbow_movement": event.average_elbow_movement or "",
        "ending_reason": event.ending_reason or "",
        "transition_type": event.transition_type or "",
        "end_transition_type": event.end_transition_type or "",
    }


def _identity_status_text(status: str) -> str:
    return {
        "manager_confirmed": "Manager confirmed",
        "appearance_matched": "Automatically appearance-matched; review recommended",
        "review_required": "Kept separate because matching was ambiguous",
        "provisional": "New provisional anonymous ID",
        "not_linked": "No global ID was established",
    }.get(status, status.replace("_", " ").title())


def _group_card(group: dict, row: dict) -> str:
    sessions: list[WorkerSession] = group["sessions"]
    events: list[ActivityEvent] = group["events"]
    media: dict[str, WorkerSnapshot] = group["media"]
    stitches: list[WorkerSessionStitch] = group.get("stitches", [])
    preview = media.get("face") or media.get("body")
    if preview:
        preview_kind = "Captured face" if preview.kind == "face" else "Body capture (face unavailable)"
        previews = (
            f"<figure><img src='{html.escape(_snapshot_url(preview), quote=True)}' "
            f"alt='{html.escape(preview_kind, quote=True)}'><figcaption>{html.escape(preview_kind)}</figcaption></figure>"
        )
    else:
        previews = "<p class='muted'>No worker face or body preview passed the quality threshold.</p>"

    activity_rows = []
    for activity, field in ACTIVITY_FIELDS.items():
        seconds = float(row.get(field, 0) or 0)
        if seconds > 0:
            activity_rows.append(
                f"<tr><td>{html.escape(ACTIVITY_LABELS[activity])}</td>"
                f"<td>{_duration_text(seconds)}</td><td>{seconds:.1f}s</td></tr>"
            )
    if not activity_rows:
        activity_rows.append("<tr><td colspan='3'>No completed activity evidence was available.</td></tr>")
    unknown_totals: defaultdict[str, float] = defaultdict(float)
    for event in events:
        if event.activity == "UNKNOWN":
            unknown_totals[
                normalize_unknown_reason(
                    "UNKNOWN", event.unknown_reason, legacy=True
                )
            ] += _event_duration(event)
    unknown_rows = "".join(
        f"<tr><td>{html.escape(reason.replace('_', ' ').title())}</td><td>{_duration_text(seconds)}</td></tr>"
        for reason, seconds in sorted(unknown_totals.items(), key=lambda item: item[1], reverse=True)
    ) or "<tr><td colspan='2'>No structured unknown reasons were recorded.</td></tr>"

    timeline_rows = []
    for event in sorted(events, key=lambda item: ensure_utc(item.start_time)):
        end = event.end_time.isoformat(sep=" ", timespec="seconds") if event.end_time else "In progress"
        timeline_rows.append(
            f"<tr><td>{event.camera_id}</td>"
            f"<td>{html.escape(event.start_time.isoformat(sep=' ', timespec='seconds'))}</td>"
            f"<td>{html.escape(end)}</td>"
            f"<td>{html.escape(ACTIVITY_LABELS.get(event.activity, event.activity.replace('_', ' ').title()))}</td>"
            f"<td>{_duration_text(_event_duration(event))}</td>"
            f"<td>{html.escape(normalize_unknown_reason(event.activity, event.unknown_reason, legacy=True) or '')}</td>"
            f"<td>{html.escape(event.review_status)}</td></tr>"
        )
    if not timeline_rows:
        timeline_rows.append("<tr><td colspan='7'>No activity events were available.</td></tr>")
    idle_rows = "".join(
        f"<tr><td>{event.camera_id}</td>"
        f"<td>{html.escape(_display_datetime(event.start_time))}</td>"
        f"<td>{html.escape(_display_datetime(event.end_time))}</td>"
        f"<td>{_duration_text(_event_duration(event))}</td>"
        f"<td>{html.escape(event.evidence_quality or 'Not recorded')}</td>"
        f"<td>{html.escape(event.ending_reason or 'Not recorded')}</td>"
        f"<td>{html.escape(event.review_status)}</td></tr>"
        for event in sorted(events, key=lambda item: ensure_utc(item.start_time))
        if event.activity == "IDLE"
    ) or "<tr><td colspan='7'>No confirmed idle interval was recorded.</td></tr>"

    session_rows = "".join(
        f"<tr><td>{session.camera_id}</td><td class='session-id'>{html.escape(session.id)}</td>"
        f"<td>{html.escape(session.first_seen.isoformat(sep=' ', timespec='seconds'))}</td>"
        f"<td>{html.escape(session.last_seen.isoformat(sep=' ', timespec='seconds'))}</td></tr>"
        for session in sessions
    )
    stitch_rows = "".join(
        f"<tr><td>{item.previous_track_id}</td><td>{item.new_track_id}</td>"
        f"<td>{item.gap_seconds:.2f}s</td><td>{item.confidence:.2f}</td>"
        f"<td>{html.escape(item.reason)}</td><td class='session-id'>{html.escape(item.original_session_id)}</td></tr>"
        for item in stitches
    ) or "<tr><td colspan='6'>No camera-local session stitching was applied.</td></tr>"
    global_id = row["global_worker_id"] or "Not established"
    confidence = (
        f"{float(row['identity_confidence']) * 100:.0f}%"
        if row["identity_confidence"] != ""
        else "Not available"
    )
    anchor = "worker-" + "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in (row["global_worker_id"] or group["sessions"][0].id)
    )
    search_text = " ".join(
        (
            row["worker_label"],
            str(row["global_worker_id"]),
            str(row["camera_ids"]),
            str(row["worker_session_ids"]),
            str(row["identity_status"]),
        )
    ).lower()
    return f"""
<article class='worker-card' id='{html.escape(anchor, quote=True)}' data-status='{html.escape(row['identity_status'], quote=True)}' data-search='{html.escape(search_text, quote=True)}'>
  <div class='worker-head'>
    <div>
      <h2>{html.escape(row['worker_label'])}</h2>
      <p class='session-id'>Global anonymous ID: {html.escape(global_id)}</p>
      <p><span class='identity identity-{html.escape(row['identity_status'])}'>{html.escape(_identity_status_text(row['identity_status']))}</span></p>
      <p class='muted'>Identity confidence: {confidence}. This is appearance association, not confirmed legal identity.</p>
    </div>
    <div class='previews'>{previews}</div>
  </div>
  <div class='facts'>
    <div><span>Cameras</span><strong>{html.escape(str(row['camera_ids']))}</strong></div>
    <div><span>Camera sessions</span><strong>{row['session_count']}</strong></div>
    <div><span>First seen</span><strong>{html.escape(row['first_seen'])}</strong></div>
    <div><span>Last seen</span><strong>{html.escape(row['last_seen'])}</strong></div>
    <div><span>Observed time (camera overlap removed)</span><strong>{html.escape(row['observed_time'])}</strong></div>
    <div><span>Confirmed work observed</span><strong>{html.escape(row['confirmed_work_time'])}</strong></div>
    <div><span>Confirmed idle</span><strong>{html.escape(row['confirmed_idle_time'])}</strong></div>
    <div><span>Idle intervals</span><strong>{row['idle_event_count']}</strong></div>
    <div><span>Reliable work percentage</span><strong>{row['reliable_work_percentage']:.1f}%</strong></div>
    <div><span>Customers served</span><strong>{row['customers_served']}</strong></div>
    <div><span>Medicine retrieval</span><strong>{_duration_text(row['medicine_retrieval_seconds'])}</strong></div>
  </div>
  <h3>What was observed</h3>
  <table><thead><tr><th>Observed activity</th><th>Hours</th><th>Seconds</th></tr></thead><tbody>{''.join(activity_rows)}</tbody></table>
  <details><summary>Unknown time by reason</summary>
    <table><thead><tr><th>Reason</th><th>Duration</th></tr></thead><tbody>{unknown_rows}</tbody></table>
  </details>
  <details><summary>Camera sessions ({len(sessions)})</summary>
    <table><thead><tr><th>Camera</th><th>Session ID</th><th>First seen</th><th>Last seen</th></tr></thead><tbody>{session_rows}</tbody></table>
  </details>
  <details><summary>Session-stitch audit ({len(stitches)})</summary>
    <table><thead><tr><th>Previous track</th><th>New track</th><th>Gap</th><th>Confidence</th><th>Reason</th><th>Original generated session ID</th></tr></thead><tbody>{stitch_rows}</tbody></table>
  </details>
  <details><summary>Evidence timeline ({len(events)} events)</summary>
    <table><thead><tr><th>Camera</th><th>Start</th><th>End</th><th>Activity</th><th>Duration</th><th>Unknown reason</th><th>Review</th></tr></thead><tbody>{''.join(timeline_rows)}</tbody></table>
  </details>
  <details><summary>Confirmed idle timeline ({row['idle_event_count']} intervals)</summary>
    <table><thead><tr><th>Camera</th><th>Start</th><th>End</th><th>Duration</th><th>Evidence quality</th><th>Ending reason</th><th>Review</th></tr></thead><tbody>{idle_rows}</tbody></table>
  </details>
</article>"""


def _manager_document(
    report_date: date,
    cards: str,
    rows: list[dict],
    session_count: int,
    customer_rows: list[dict],
    customer_summary: dict,
    camera_count: int,
    active_worker_sessions: int,
    unknown_totals: dict[str, float],
    idle_events: list[ActivityEvent],
) -> str:
    total_observed = sum(float(row["observed_seconds"]) for row in rows)
    total_work = sum(float(row["confirmed_work_seconds"]) for row in rows)
    established_global_ids = sum(1 for row in rows if row["global_worker_id"])
    multi_camera = sum(1 for row in rows if len(str(row["camera_ids"]).split(",")) > 1)
    review_required = sum(
        1 for row in rows if row["identity_status"] in {"review_required", "appearance_matched"}
    )
    trusted_customer_rows = [
        row for row in customer_rows if row["trust_classification"] == "trusted_completed"
    ]
    total_customer_service = sum(
        float(row["service_seconds"]) for row in trusted_customer_rows
    )
    total_shelf = sum(float(row["shelf_work_seconds"]) for row in rows)
    total_phone = sum(float(row["confirmed_phone_seconds"]) for row in rows)
    total_possible_phone = sum(float(row["possible_phone_seconds"]) for row in rows)
    total_possible_idle = sum(float(row["possible_idle_seconds"]) for row in rows)
    total_idle = sum(float(row["confirmed_idle_seconds"]) for row in rows)
    total_unknown = sum(float(row["unknown_activity_seconds"]) for row in rows)
    reliable_seconds = total_work + total_idle + total_phone
    classified_or_review = (
        reliable_seconds + total_unknown + total_possible_phone + total_possible_idle
    )
    reliable_percent = (
        round(100 * reliable_seconds / classified_or_review, 1)
        if classified_or_review
        else None
    )
    reliable_work_percent = (
        round(100 * total_work / reliable_seconds, 1) if reliable_seconds else None
    )
    idle_durations = [_event_duration(event) for event in idle_events]
    unknown_with_reason = total_unknown - float(
        unknown_totals.get("legacy_record_missing_reason", 0) or 0
    )
    unknown_reason_coverage = (
        round(100 * max(0.0, unknown_with_reason) / total_unknown, 1)
        if total_unknown
        else 100.0
    )
    customer_table_rows = "".join(
        f"<tr><td class='session-id'>{html.escape(str(item['customer_session_id']))}</td>"
        f"<td>{item['camera_id']}</td><td>{html.escape(str(item['arrival_display']))}</td>"
        f"<td>{html.escape(str(item['waiting_duration']))}</td>"
        f"<td>{html.escape(str(item['service_started_display'] or 'Not started'))}</td>"
        f"<td>{html.escape(str(item['total_service_duration']))}</td>"
        f"<td>{html.escape(str(item['direct_interaction_duration']))}</td>"
        f"<td>{html.escape(str(item['medicine_retrieval_duration']))}</td>"
        f"<td class='session-id'>{html.escape(str(item['assigned_worker_session_id'] or 'Unassigned'))}</td>"
        f"<td>{html.escape(str(item['outcome']))}</td>"
        f"<td>{html.escape(str(item['trust_classification']))}</td>"
        f"<td>{html.escape(str(item['review_status']))}</td></tr>"
        for item in customer_rows
    ) or "<tr><td colspan='12'>No customer journey was persisted for this date. Configure queue/service zones to enable timing.</td></tr>"
    unknown_rows = "".join(
        f"<tr><td>{html.escape(reason.replace('_', ' ').title())}</td><td>{_duration_text(seconds)}</td></tr>"
        for reason, seconds in sorted(unknown_totals.items(), key=lambda item: item[1], reverse=True)
    ) or "<tr><td colspan='2'>No structured unknown reasons were recorded.</td></tr>"
    overview_rows = "".join(
        (
            f"<tr class='overview-row' data-status='{html.escape(row['identity_status'], quote=True)}' "
            f"data-search='{html.escape((' '.join((row['worker_label'], str(row['global_worker_id']), str(row['camera_ids']), str(row['worker_session_ids'])))).lower(), quote=True)}'>"
            f"<td><a href='#worker-{html.escape(''.join(character if character.isalnum() or character in '-_' else '-' for character in (row['global_worker_id'] or str(row['worker_session_ids']).split(',')[0])), quote=True)}'>{html.escape(row['worker_label'])}</a></td>"
            f"<td class='session-id'>{html.escape(row['global_worker_id'] or 'Not established')}</td>"
            f"<td>{html.escape(str(row['camera_ids']))}</td>"
            f"<td>{html.escape(_identity_status_text(row['identity_status']))}</td>"
            f"<td>{html.escape(row['observed_time'])}</td>"
            f"<td>{html.escape(row['confirmed_work_time'])}</td>"
            f"<td>{html.escape(row['confirmed_idle_time'])}</td>"
            f"<td>{_duration_text(row['possible_phone_seconds'])}</td>"
            f"<td>{_duration_text(row['unknown_activity_seconds'])}</td>"
            f"<td>{float(row['classification_coverage_percent']):.1f}%</td></tr>"
        )
        for row in rows
    )
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>Worker Activity Report</title>
<style>
body{{font:15px system-ui;max-width:1180px;margin:36px auto;padding:0 18px;color:#17342d;background:#f6f8f6}}
h1,h2,h3{{color:#075e54}} article,.summary,.note,.glossary{{background:white;padding:20px;margin:14px 0;border:1px solid #d9e3df;border-radius:12px}}
.summary-grid,.facts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}}
.summary-grid div,.facts div{{background:#f4f8f6;padding:12px;border-radius:8px}} .facts span{{display:block;color:#59716a;font-size:13px}}
.summary-grid span,.summary-grid strong{{display:block}} .summary-grid span{{color:#425b54;font-size:13px}} .summary-grid strong,.facts strong{{display:block;margin-top:5px;font-size:20px}} .worker-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;flex-wrap:wrap}}
.session-id{{font-family:ui-monospace,monospace;overflow-wrap:anywhere}} .previews{{display:flex;gap:12px;flex-wrap:wrap}} figure{{margin:0}}
img{{width:180px;height:140px;object-fit:contain;background:#eaf0ed;border-radius:9px}} figcaption,.muted{{color:#59716a;font-size:13px}}
table{{width:100%;border-collapse:collapse;margin-top:8px}} th,td{{text-align:left;padding:9px;border-bottom:1px solid #dde5e1;vertical-align:top}}
details{{margin-top:16px}} summary{{cursor:pointer;font-weight:700;color:#075e54}} .note{{border-left:4px solid #c57b00}}
.identity{{display:inline-block;padding:5px 9px;border-radius:999px;background:#eef2f0;font-weight:700}} .identity-manager_confirmed{{background:#dff3e8;color:#176343}}
.identity-review_required,.identity-appearance_matched{{background:#fff0ce;color:#805000}}
.filters{{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}} input,select{{font:inherit;padding:10px 12px;border:1px solid #b8c8c1;border-radius:8px;background:white}} #workerSearch{{flex:1;min-width:320px}}
.overview{{max-height:520px;overflow:auto;border:1px solid #d9e3df;border-radius:8px}} a{{color:#075e54;font-weight:700}} .hidden{{display:none}}
</style></head><body>
<h1>Pharmacy Operations and Worker Activity Report</h1>
<p>Report date: {report_date.isoformat()}</p>
<section class='summary'><h2>Business summary</h2><div class='summary-grid'>
  <div><span>Cameras processed</span><strong>{camera_count}</strong></div>
  <div><span>Worker groups in report</span><strong>{len(rows)}</strong></div>
  <div><span>Active worker sessions</span><strong>{active_worker_sessions}</strong></div>
  <div><span>Global anonymous IDs established</span><strong>{established_global_ids}</strong></div>
  <div><span>Camera-local worker sessions</span><strong>{session_count}</strong></div>
  <div><span>Workers seen on multiple cameras</span><strong>{multi_camera}</strong></div>
  <div><span>Identity associations to review</span><strong>{review_required}</strong></div>
  <div><span>Trusted worker groups</span><strong>{sum(row['quality_status'] not in {'review_required', 'appearance_matched'} for row in rows)}</strong></div>
  <div><span>Trusted completed services</span><strong>{customer_summary.get('trusted_completed_services', 0)}</strong></div>
  <div><span>Completed services requiring review</span><strong>{customer_summary.get('completed_services_requiring_review', 0)}</strong></div>
  <div><span>Legacy incomplete services</span><strong>{customer_summary.get('legacy_incomplete_services', 0)}</strong></div>
  <div><span>Customers currently waiting</span><strong>{customer_summary.get('customers_currently_waiting', 0)}</strong></div>
  <div><span>Average waiting time</span><strong>{_duration_text(customer_summary.get('average_wait_seconds'))}</strong></div>
  <div><span>Median waiting time</span><strong>{_duration_text(customer_summary.get('median_wait_seconds'))}</strong></div>
  <div><span>Longest waiting time</span><strong>{_duration_text(customer_summary.get('longest_wait_seconds'))}</strong></div>
  <div><span>Average service time</span><strong>{_duration_text(customer_summary.get('average_service_seconds'))}</strong></div>
  <div><span>Median service time</span><strong>{_duration_text(customer_summary.get('median_service_seconds'))}</strong></div>
  <div><span>Longest service time</span><strong>{_duration_text(customer_summary.get('longest_service_seconds'))}</strong></div>
  <div><span>Average medicine retrieval</span><strong>{_duration_text(customer_summary.get('average_medicine_retrieval_seconds'))}</strong></div>
  <div><span>Abandoned customers</span><strong>{customer_summary.get('abandoned_customers', 0)}</strong></div>
  <div><span>Total confirmed work</span><strong>{_duration_text(total_work)}</strong></div>
  <div><span>Total customer-service time</span><strong>{_duration_text(total_customer_service)}</strong></div>
  <div><span>Total shelf-work time</span><strong>{_duration_text(total_shelf)}</strong></div>
  <div><span>Confirmed idle time</span><strong>{_duration_text(total_idle)}</strong></div>
  <div><span>Confirmed idle intervals</span><strong>{len(idle_events)}</strong></div>
  <div><span>Workers with confirmed idle</span><strong>{sum(float(row['confirmed_idle_seconds']) > 0 for row in rows)}</strong></div>
  <div><span>Average idle interval</span><strong>{_duration_text(statistics.fmean(idle_durations) if idle_durations else 0)}</strong></div>
  <div><span>Median idle interval</span><strong>{_duration_text(statistics.median(idle_durations) if idle_durations else 0)}</strong></div>
  <div><span>Longest idle interval</span><strong>{_duration_text(max(idle_durations) if idle_durations else 0)}</strong></div>
  <div><span>Confirmed phone time</span><strong>{_duration_text(total_phone)}</strong></div>
  <div><span>Possible phone — review</span><strong>{_duration_text(total_possible_phone)}</strong></div>
  <div><span>Possible idle — review</span><strong>{_duration_text(total_possible_idle)}</strong></div>
  <div><span>Unknown time</span><strong>{_duration_text(total_unknown)}</strong></div>
  <div><span>Reliable classification coverage (Observed time not requiring review)</span><strong>{f'{reliable_percent:.1f}%' if reliable_percent is not None else 'Unavailable'}</strong></div>
  <div><span>Reliable work percentage</span><strong>{f'{reliable_work_percent:.1f}%' if reliable_work_percent is not None else 'Unavailable'}</strong></div>
  <div><span>UNKNOWN time with recorded reason</span><strong>{unknown_reason_coverage:.1f}%</strong></div>
</div></section>
<section class='summary'><h2>Customer-service journeys</h2>
<p>Waiting ends when a primary worker assignment is confirmed. Total service continues while that worker retrieves medicine and returns.</p>
<div class='overview'><table><thead><tr><th>Customer session</th><th>Camera</th><th>Arrival (UTC)</th><th>Waiting</th><th>Service start (UTC)</th><th>Total service</th><th>Direct interaction</th><th>Medicine retrieval</th><th>Assigned worker</th><th>Outcome</th><th>Trust</th><th>Review</th></tr></thead><tbody>{customer_table_rows}</tbody></table></div>
</section>
<section class='summary'><h2>Worker overview</h2>
<p>Use this table first. Search by worker label, global ID, session ID, or camera; then open a worker's detailed evidence card.</p>
<div class='filters'><input id='workerSearch' type='search' placeholder='Search workers, IDs, sessions, cameras' aria-label='Search workers'>
<select id='identityFilter' aria-label='Filter by identity status'><option value=''>All identity statuses</option><option value='manager_confirmed'>Manager confirmed</option><option value='appearance_matched'>Appearance matched</option><option value='review_required'>Review required</option><option value='provisional'>Provisional</option><option value='not_linked'>Not linked</option></select></div>
<div class='overview'><table><thead><tr><th>Worker</th><th>Global ID</th><th>Cameras</th><th>Identity status</th><th>Observed</th><th>Work observed</th><th>Confirmed idle</th><th>Possible phone</th><th>Unknown</th><th>Reliable coverage</th></tr></thead><tbody>{overview_rows or '<tr><td colspan="10">No workers were observed.</td></tr>'}</tbody></table></div>
</section>
{cards or "<section><p>No worker sessions were available for this date.</p></section>"}
<section class='summary'><h2>Unknown time by reason</h2>
<p>These reasons explain missing or weak evidence; none of them means the worker was inactive.</p>
<table><thead><tr><th>Reason</th><th>Duration</th></tr></thead><tbody>{unknown_rows}</tbody></table>
</section>
<section class='glossary'><h2>Plain-language guide</h2>
<p><strong>Worker groups in report</strong> counts conservative anonymous groups. Until strong local or cross-camera evidence links sessions, one person can appear in more than one group.</p>
<p><strong>Work observed</strong> means the cameras captured positive work evidence in configured work zones. It is not a complete productivity score.</p>
<p><strong>Confirmed physical-phone evidence</strong> requires repeated associated phone-object observations. <strong>Possible phone</strong> remains uncertain and requires human review.</p>
<p><strong>Confirmed idle</strong> requires stable visible tracking, reliable low movement, configured zones, no work/service evidence, and a sustained confirmation window. <strong>Possible idle</strong> requires review.</p>
<p><strong>Unknown / insufficient evidence</strong> means the system could not determine an activity. It does not mean the worker was inactive.</p>
<p><strong>Customer service timing</strong> depends on configured queue, service, shelf/medicine, and POS zones plus the assignment evidence rules.</p>
<p><strong>Global anonymous ID</strong> groups camera sessions using encrypted clothing/body appearance. It is not legal identity, is limited to one day, and can be wrong when uniforms look alike.</p>
</section>
<section class='note'><h2>Important limitations</h2>
<p>Camera-observed time is not payroll, attendance, discipline, or a complete record of a shift. Overlapping camera-session intervals for one global ID are counted once.</p>
<p>Automatic appearance matches use a strict distance threshold and second-best margin. Ambiguous people are kept separate instead of silently merged. A manager can confirm or correct an association through the worker-identity review API.</p>
<p>Captured face images are visual previews for authorized managers only. No face recognition or embeddings are used for faces. Appearance descriptors are encrypted, short-lived, worker-only, and never created for customers.</p>
<p>UNKNOWN does not mean inactive. Possible phone and possible idle require review. Anonymous appearance matching is not confirmed identity. CCTV evidence is not payroll or disciplinary proof.</p>
</section>
<script>
const search = document.getElementById('workerSearch');
const identityFilter = document.getElementById('identityFilter');
function applyFilters() {{
  const term = search.value.trim().toLowerCase();
  const status = identityFilter.value;
  document.querySelectorAll('.worker-card,.overview-row').forEach((item) => {{
    const matchesText = !term || (item.dataset.search || '').includes(term);
    const matchesStatus = !status || item.dataset.status === status;
    item.classList.toggle('hidden', !(matchesText && matchesStatus));
  }});
}}
search.addEventListener('input', applyFilters);
identityFilter.addEventListener('change', applyFilters);
</script>
</body></html>"""


def generate_reports(db: Session, report_date: date) -> dict:
    """Build customer- and worker-centric reports without changing captured data."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    start, end = day_bounds(report_date)
    events = db.scalars(
        select(ActivityEvent)
        .where(ActivityEvent.start_time >= start, ActivityEvent.start_time <= end)
        .order_by(ActivityEvent.start_time)
    ).all()
    sessions = db.scalars(
        select(WorkerSession)
        .where(WorkerSession.first_seen >= start, WorkerSession.first_seen <= end)
        .order_by(WorkerSession.first_seen)
    ).all()
    customer_sessions = db.scalars(
        select(CustomerSession)
        .where(
            CustomerSession.waiting_started_at >= start,
            CustomerSession.waiting_started_at <= end,
        )
        .order_by(CustomerSession.waiting_started_at)
    ).all()
    session_ids = [session.id for session in sessions]
    snapshots = (
        db.scalars(
            select(WorkerSnapshot).where(WorkerSnapshot.worker_session_id.in_(session_ids))
        ).all()
        if session_ids
        else []
    )
    stitches = (
        db.scalars(
            select(WorkerSessionStitch).where(
                WorkerSessionStitch.canonical_worker_session_id.in_(session_ids)
            )
        ).all()
        if session_ids
        else []
    )
    links = (
        db.scalars(
            select(WorkerIdentityLink).where(
                WorkerIdentityLink.worker_session_id.in_(session_ids)
            )
        ).all()
        if session_ids
        else []
    )
    links_by_session = {link.worker_session_id: link for link in links}
    identity_ids = {link.worker_identity_id for link in links}
    identities = (
        db.scalars(select(WorkerIdentity).where(WorkerIdentity.id.in_(identity_ids))).all()
        if identity_ids
        else []
    )
    identity_by_id = {identity.id: identity for identity in identities}
    session_by_id = {session.id: session for session in sessions}
    events_by_session: defaultdict[str, list[ActivityEvent]] = defaultdict(list)
    for event in events:
        events_by_session[event.worker_session_id].append(event)
    snapshots_by_session: defaultdict[str, list[WorkerSnapshot]] = defaultdict(list)
    for snapshot in snapshots:
        snapshots_by_session[snapshot.worker_session_id].append(snapshot)
    customers_by_worker: defaultdict[str, list[CustomerSession]] = defaultdict(list)
    for customer in customer_sessions:
        if customer.worker_session_id:
            customers_by_worker[customer.worker_session_id].append(customer)
    stitches_by_session: defaultdict[str, list[WorkerSessionStitch]] = defaultdict(list)
    for stitch in stitches:
        stitches_by_session[stitch.canonical_worker_session_id].append(stitch)

    groups: dict[str, dict] = {}
    for session in sessions:
        link = links_by_session.get(session.id)
        group_key = link.worker_identity_id if link else f"SESSION:{session.id}"
        group = groups.setdefault(
            group_key,
            {
                "identity": identity_by_id.get(link.worker_identity_id) if link else None,
                "sessions": [],
                "links": [],
                "events": [],
                "snapshots": [],
                "customer_sessions": [],
                "stitches": [],
            },
        )
        group["sessions"].append(session)
        if link:
            group["links"].append(link)
        group["events"].extend(events_by_session[session.id])
        group["snapshots"].extend(snapshots_by_session[session.id])
        group["customer_sessions"].extend(customers_by_worker[session.id])
        group["stitches"].extend(stitches_by_session[session.id])

    worker_rows = []
    cards = []
    for group in groups.values():
        row = _group_row(report_date, group)
        worker_rows.append(row)
        cards.append(_group_card(group, row))
    event_rows = [
        _event_row(
            event,
            session_by_id[event.worker_session_id],
            identity_by_id.get(links_by_session[event.worker_session_id].worker_identity_id)
            if event.worker_session_id in links_by_session
            else None,
            links_by_session.get(event.worker_session_id),
        )
        for event in events
        if event.worker_session_id in session_by_id
    ]
    customer_rows = [_customer_row(session) for session in customer_sessions]
    customer_summary = customer_metrics(customer_sessions)
    unknown_totals: defaultdict[str, float] = defaultdict(float)
    for event in events:
        if event.activity == "UNKNOWN" and event.review_status != "false_alarm":
            unknown_totals[
                normalize_unknown_reason(
                    "UNKNOWN", event.unknown_reason, legacy=True
                )
            ] += _event_duration(event)
    camera_count = len(
        {session.camera_id for session in sessions}
        | {session.camera_id for session in customer_sessions}
    )
    document = _manager_document(
        report_date,
        "".join(cards),
        worker_rows,
        len(sessions),
        customer_rows,
        customer_summary,
        camera_count,
        sum(
            session.ended_at is None
            and ensure_utc(session.last_seen)
            >= datetime.now(UTC) - timedelta(seconds=60)
            for session in sessions
        ),
        dict(unknown_totals),
        [
            event
            for event in events
            if event.activity == "IDLE" and event.review_status != "false_alarm"
        ],
    )

    paths = {
        "summary_csv": REPORT_DIR / "latest_report.csv",
        "events_csv": REPORT_DIR / "latest_events.csv",
        "customer_csv": REPORT_DIR / "latest_customer_report.csv",
        "manager_html": REPORT_DIR / "latest_manager_report.html",
    }
    with TemporaryDirectory(dir=REPORT_DIR, prefix=".report-build-") as temporary_directory:
        staging = Path(temporary_directory)
        staged_paths = {key: staging / path.name for key, path in paths.items()}
        _csv(staged_paths["summary_csv"], worker_rows, WORKER_HEADERS)
        _csv(staged_paths["events_csv"], event_rows, EVENT_HEADERS)
        _csv(staged_paths["customer_csv"], customer_rows, CUSTOMER_HEADERS)
        staged_paths["manager_html"].write_text(document, encoding="utf-8")
        current_paths = set(paths.values())
        uploaded, sheets_error = upload_aggregates(worker_rows)
        if not settings.google_sheets_enabled or uploaded:
            _remove_obsolete_exports(current_paths)
        for key, path in paths.items():
            os.replace(staged_paths[key], path)

    return {
        "success": True,
        "local_reports_created": True,
        "google_sheets_uploaded": uploaded,
        "google_sheets_error": sheets_error,
        "files": {key: str(path) for key, path in paths.items()},
    }
