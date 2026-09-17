from services.activity_engine import ActivityEngine
from services.evidence_service import ActivityEvidence, evidence_status
from services.state_machine import TemporalStateMachine


def test_state_priority_and_pose_alone_is_only_possible_phone():
    engine = ActivityEngine()
    evidence = ActivityEvidence(
        camera_healthy=True,
        phone_like_pose=True,
        cashier=True,
        evidence_quality="MEDIUM",
    )
    assert engine.choose(evidence) == "CASHIER_WORK"
    evidence.cashier = False
    assert engine.choose(evidence) == "POSSIBLE_PHONE"


def test_physical_confirmation_is_on_phone():
    evidence = ActivityEvidence(
        camera_healthy=True,
        physical_phone_confirmed=True,
        serving_customer=True,
        evidence_quality="MEDIUM",
    )
    assert ActivityEngine().choose(evidence) == "SERVING_CUSTOMER"
    evidence.serving_customer = False
    assert ActivityEngine().choose(evidence) == "ON_PHONE"


def test_camera_failure_exclusion_and_unknown_remains_valid():
    evidence = ActivityEvidence(camera_healthy=False, low_movement_seconds=999)
    assert ActivityEngine().choose(evidence) == "UNKNOWN"
    evidence.camera_healthy = True; evidence.low_movement_seconds = 0
    assert ActivityEngine().choose(evidence) == "UNKNOWN"


def test_reliable_low_motion_becomes_internal_idle_candidate():
    evidence = ActivityEvidence(
        camera_healthy=True,
        low_motion_confirmed=True,
        evidence_quality="MEDIUM",
    )
    assert ActivityEngine().choose(evidence) == "IDLE_CANDIDATE"
    evidence.idle_blocking_reasons = ["service is active"]
    assert ActivityEngine().choose(evidence) == "UNKNOWN"


def test_manager_evidence_status_never_infers_not_working():
    assert evidence_status("WORKER", "SHELF_WORK") == "WORK_OBSERVED"
    assert evidence_status("WORKER", "POSSIBLE_IDLE") == "REVIEW_NEEDED"
    assert evidence_status("WORKER", "UNKNOWN") == "INSUFFICIENT_EVIDENCE"
    assert evidence_status("CUSTOMER", "UNKNOWN") == "CUSTOMER_OBSERVED"


def test_temporal_confirmation_avoids_one_frame_events():
    machine = TemporalStateMachine(confirm_seconds=1.5)
    assert machine.update(7, "CASHIER_WORK", 0) is None
    assert machine.update(7, "CASHIER_WORK", 1) is None
    transition = machine.update(7, "CASHIER_WORK", 1.5)
    assert transition.current == "CASHIER_WORK"
