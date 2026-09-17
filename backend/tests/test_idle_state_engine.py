from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import select

from db_models.activity_event import ActivityEvent
from db_models.camera import Camera
from db_models.camera_session import CameraSession
from db_models.worker_session import WorkerSession
from services.activity_engine import ActivityEngine
from services.customer_analytics import customer_trust_classification
from services.evidence_service import (
    ActivityEvidence,
    EvidenceQuality,
    UnknownReason,
    assess_evidence_quality,
    normalize_unknown_reason,
)
from services.event_service import EventContext, EventService
from services.state_machine import TemporalStateMachine
from services.work_motion_service import TemporalWorkMotion


def _pose() -> SimpleNamespace:
    points = [(50.0, 50.0, 0.9)] * 17
    points[5] = (40.0, 55.0, 0.9)
    points[6] = (60.0, 55.0, 0.9)
    points[7] = (42.0, 75.0, 0.9)
    points[8] = (58.0, 75.0, 0.9)
    points[9] = (42.0, 95.0, 0.9)
    points[10] = (58.0, 95.0, 0.9)
    points[11] = (45.0, 110.0, 0.9)
    points[12] = (55.0, 110.0, 0.9)
    return SimpleNamespace(global_keypoints=points, status="VALID")


def _idle_evidence(**changes) -> ActivityEvidence:
    values = {
        "camera_healthy": True,
        "low_motion_confirmed": True,
        "evidence_quality": EvidenceQuality.MEDIUM.value,
        "track_age_seconds": 20.0,
        "track_stable": True,
    }
    values.update(changes)
    return ActivityEvidence(**values)


def test_stable_worker_becomes_idle_candidate_and_then_confirmed(monkeypatch):
    monkeypatch.setattr("services.state_machine.settings.idle_confirm_seconds", 15.0)
    engine = ActivityEngine()
    machine = TemporalStateMachine(confirm_seconds=0)

    assert engine.choose(_idle_evidence()) == "IDLE_CANDIDATE"
    assert machine.update(
        1, "IDLE_CANDIDATE", 20.0, evidence_quality="MEDIUM"
    ) is None
    assert machine.diagnostics(1, 34.9)["idle_candidate_seconds"] == 14.9
    transition = machine.update(
        1, "IDLE_CANDIDATE", 35.0, evidence_quality="MEDIUM"
    )
    assert transition is not None and transition.current == "IDLE"
    assert machine.diagnostics(1, 50.0)["confirmed_idle_seconds"] == 15.0


def test_controlled_work_idle_work_timeline_confirms_about_30_seconds(monkeypatch):
    monkeypatch.setattr("services.state_machine.settings.idle_confirm_seconds", 15.0)
    machine = TemporalStateMachine(confirm_seconds=0)
    observed: list[str] = []
    transitions = []

    # Establish the initial state without advancing the controlled clock.
    machine.update(1, "OTHER_WORK", 0.0, evidence_quality="HIGH")
    machine.update(1, "OTHER_WORK", 0.0, evidence_quality="HIGH")

    for second in range(90):
        proposed = (
            "OTHER_WORK"
            if second < 20 or second >= 65
            else "IDLE_CANDIDATE"
        )
        transition = machine.update(
            1,
            proposed,
            float(second),
            evidence_quality="HIGH",
            exit_reason=(
                "confirmed work resumed" if second >= 65 else None
            ),
        )
        if transition is not None:
            transitions.append(transition)
        diagnostics = machine.diagnostics(1, float(second))
        observed.append(
            "IDLE_CANDIDATE"
            if diagnostics["candidate_activity"] == "IDLE_CANDIDATE"
            else diagnostics["final_activity"]
        )

    assert observed[:20] == ["OTHER_WORK"] * 20
    assert observed[20:35] == ["IDLE_CANDIDATE"] * 15
    assert observed[35:65] == ["IDLE"] * 30
    assert observed[65:] == ["OTHER_WORK"] * 25
    assert [(item.previous, item.current, item.at) for item in transitions] == [
        ("OTHER_WORK", "IDLE", 35.0),
        ("IDLE", "OTHER_WORK", 65.0),
    ]


def test_service_retrieval_shelf_and_pos_prevent_idle():
    engine = ActivityEngine()
    for field, expected in (
        ("serving_customer", "SERVING_CUSTOMER"),
        ("fetching_medicine", "FETCHING_MEDICINE"),
        ("shelf", "SHELF_WORK"),
        ("computer_pos", "COMPUTER_POS_WORK"),
    ):
        evidence = _idle_evidence(**{field: True})
        assert engine.choose(evidence) == expected


def test_low_quality_evidence_stays_unknown():
    evidence = _idle_evidence(evidence_quality=EvidenceQuality.LOW.value)
    assert ActivityEngine().choose(evidence) == "UNKNOWN"


def test_config_can_require_high_quality_before_idle_candidate(monkeypatch):
    monkeypatch.setattr(
        "services.evidence_service.settings.idle_min_evidence_quality", "HIGH"
    )
    assert ActivityEngine().choose(_idle_evidence()) == "UNKNOWN"
    assert ActivityEngine().choose(
        _idle_evidence(evidence_quality=EvidenceQuality.HIGH.value)
    ) == "IDLE_CANDIDATE"


def test_missing_pose_can_be_medium_when_bbox_motion_is_reliable():
    assessment = assess_evidence_quality(
        track_confirmed=True,
        track_age_seconds=20,
        confidence=0.9,
        crop_width=80,
        crop_height=180,
        zones_configured=True,
        confirmed_zones={"employee_area"},
        pose_status="MISSING",
        pose_confident_points=0,
        bbox_motion_reliable=True,
        minimum_track_age_seconds=5,
    )
    assert assessment.quality == EvidenceQuality.MEDIUM
    assert assessment.unknown_reason == UnknownReason.POSE_MISSING.value
    assert not assessment.idle_blocking_reasons


def test_small_bbox_jitter_and_one_missing_pose_do_not_reset_low_motion():
    motion = TemporalWorkMotion()
    base = (0.0, 0.0, 100.0, 160.0)
    motion.update(1, _pose(), base, 0.0)
    second = motion.update(1, _pose(), (1.0, 0.0, 101.0, 160.0), 1.0)
    missing = motion.update(1, None, (2.0, 0.0, 102.0, 160.0), 2.0)
    assert second.low_motion
    assert missing.low_motion and missing.low_motion_seconds >= 1.0
    assert not missing.pose_reliable and missing.bbox_reliable
    assert missing.pose_temporarily_missing
    after_grace = motion.update(1, None, (3.0, 0.0, 103.0, 160.0), 6.0)
    assert not after_grace.pose_temporarily_missing


def test_meaningful_movement_exits_idle_after_hysteresis(monkeypatch):
    monkeypatch.setattr(
        "services.state_machine.settings.idle_exit_confirm_seconds", 1.5
    )
    machine = TemporalStateMachine(confirm_seconds=0)
    machine.states[1] = SimpleNamespace(
        current_state="IDLE",
        candidate_state=None,
        candidate_started_at=None,
        state_started_at=35.0,
        confidence=0.9,
        reasons=[],
        limitations=[],
        evidence_quality="HIGH",
        idle_blocking_reasons=[],
        last_candidate_cancel_reason=None,
        confirmation_seconds=15.0,
    )
    assert machine.update(
        1,
        "UNKNOWN",
        65.0,
        evidence_quality="HIGH",
        exit_reason="meaningful movement resumed",
    ) is None
    transition = machine.update(
        1,
        "UNKNOWN",
        66.5,
        evidence_quality="HIGH",
        exit_reason="meaningful movement resumed",
    )
    assert transition is not None and transition.current == "UNKNOWN"


def test_short_track_gap_rebind_preserves_idle_candidate(monkeypatch):
    monkeypatch.setattr("services.state_machine.settings.idle_confirm_seconds", 15.0)
    machine = TemporalStateMachine()
    machine.update(4, "IDLE_CANDIDATE", 20.0, evidence_quality="MEDIUM")
    assert machine.rebind(4, 11)
    transition = machine.update(
        11, "IDLE_CANDIDATE", 35.0, evidence_quality="MEDIUM"
    )
    assert transition is not None and transition.current == "IDLE"


def test_unknown_reason_is_mandatory_and_legacy_blank_is_explicit():
    assert normalize_unknown_reason("UNKNOWN", None) == (
        "insufficient_temporal_evidence"
    )
    assert normalize_unknown_reason("UNKNOWN", None, legacy=True) == (
        "legacy_record_missing_reason"
    )
    assert normalize_unknown_reason("SHELF_WORK", None) is None


def test_idle_interval_is_opened_and_closed_once_with_motion_evidence(db):
    now = datetime(2026, 8, 3, tzinfo=UTC)
    db.add(Camera(id=1, name="Counter", source="demo://sample"))
    db.add(CameraSession(id="CS-1", camera_id=1, source_type="demo"))
    db.add(
        WorkerSession(
            id="WS-1",
            camera_id=1,
            camera_session_id="CS-1",
            track_id=7,
            display_name="Worker 1",
            first_seen=now,
            last_seen=now + timedelta(seconds=90),
        )
    )
    db.flush()
    context = EventContext("WS-1", 7, 1, "CS-1")
    events = EventService(db)
    events.open(context, "OTHER_WORK", "VISIBLE", now, 0.9)
    events.transition(
        context,
        "IDLE",
        "VISIBLE",
        now + timedelta(seconds=35),
        0.9,
        evidence={
            "idle_confirmation_seconds": 15,
            "evidence_quality": "HIGH",
        },
    )
    events.observe(
        7,
        {
            "evidence_quality": "HIGH",
            "body_motion": 0.01,
            "wrist_motion": 0.02,
            "elbow_motion": 0.015,
        },
    )
    closed, _ = events.transition(
        context,
        "OTHER_WORK",
        "VISIBLE",
        now + timedelta(seconds=65),
        0.9,
        ending_reason="confirmed work resumed",
    )
    assert closed.activity == "IDLE" and closed.duration_seconds == 30
    assert closed.transition_type == "IDLE_STARTED"
    assert closed.end_transition_type == "IDLE_ENDED"
    assert closed.ending_reason == "confirmed work resumed"
    assert closed.average_body_movement == 0.01
    assert len(db.scalars(
        __import__("sqlalchemy").select(ActivityEvent).where(
            ActivityEvent.activity == "IDLE"
        )
    ).all()) == 1


def test_subminimum_confirmed_idle_interval_is_not_persisted(db, monkeypatch):
    monkeypatch.setattr("services.event_service.settings.idle_min_event_seconds", 2.0)
    now = datetime(2026, 8, 3, tzinfo=UTC)
    db.add(Camera(id=1, name="Counter", source="demo://sample"))
    db.add(CameraSession(id="CS-SHORT", camera_id=1, source_type="demo"))
    db.add(
        WorkerSession(
            id="WS-SHORT",
            camera_id=1,
            camera_session_id="CS-SHORT",
            track_id=1,
            display_name="Worker 1",
            first_seen=now,
            last_seen=now + timedelta(seconds=1),
        )
    )
    db.commit()
    events = EventService(db)
    events.open(
        EventContext("WS-SHORT", 1, 1, "CS-SHORT"),
        "IDLE",
        "VISIBLE",
        now,
        0.9,
    )
    events.close(1, now + timedelta(seconds=1), "camera_processing_ended")
    db.commit()
    assert not db.scalars(
        select(ActivityEvent).where(ActivityEvent.worker_session_id == "WS-SHORT")
    ).all()


def test_customer_trust_classification_excludes_incomplete_completion():
    now = datetime(2026, 8, 3, tzinfo=UTC)
    trusted = SimpleNamespace(
        outcome="COMPLETED",
        completed=True,
        service_started_at=now,
        service_completed_at=now + timedelta(seconds=30),
        service_seconds=30,
        worker_session_id="WS-1",
        current_phase="COMPLETED",
        assignment_confidence=0.9,
        review_status="unreviewed",
    )
    incomplete = SimpleNamespace(
        **{**trusted.__dict__, "service_completed_at": None, "current_phase": "WAITING"}
    )
    assert customer_trust_classification(trusted) == "trusted_completed"
    assert customer_trust_classification(incomplete) == "legacy_incomplete"
