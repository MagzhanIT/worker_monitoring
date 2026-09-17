from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from services.customer_analytics import (
    CustomerAnalyticsService,
    CustomerObservation,
    WorkerObservation,
    customer_metrics,
)


def customer(track_id=10, zones=None):
    return CustomerObservation(
        track_id,
        (100, 100, 160, 240),
        set(zones or {"customer_area", "service_position"}),
        0.9,
        1,
    )


def worker(session_id="WS-1", track_id=20, zones=None, box=None):
    return WorkerObservation(
        session_id,
        track_id,
        box or (150, 100, 210, 240),
        set(zones or {"service_position"}),
        0.9,
    )


def test_wait_service_retrieval_return_and_customer_departure_is_one_journey():
    service = CustomerAnalyticsService(start_confirm_seconds=0, customer_lost_seconds=5)
    start = datetime(2026, 7, 25, 10, 20, tzinfo=UTC)
    service.update_scene([customer()], [], start, 180)
    session = service.active[10]
    assert session.current_phase == "WAITING"

    service.update_scene([customer()], [worker()], start + timedelta(seconds=18), 180)
    assert session.waiting_seconds == 18
    assert session.current_phase == "SERVING_AT_COUNTER"

    service.update_scene(
        [customer()],
        [worker(zones={"medicine_shelf"}, box=(500, 100, 560, 240))],
        start + timedelta(seconds=43),
        180,
    )
    assert session.current_phase == "FETCHING_MEDICINE"

    service.update_scene([customer()], [worker()], start + timedelta(seconds=80), 180)
    assert session.current_phase == "SERVING_AT_COUNTER"
    finished = service.leave(10, start + timedelta(seconds=115))

    assert finished.completed and finished.outcome == "COMPLETED"
    assert finished.service_seconds == 97
    assert finished.medicine_retrieval_seconds == 37
    assert finished.direct_interaction_seconds == 60


def test_return_walk_remains_part_of_medicine_retrieval_not_direct_interaction():
    service = CustomerAnalyticsService(start_confirm_seconds=0)
    start = datetime(2026, 7, 25, 10, 0, tzinfo=UTC)
    service.update_scene([customer()], [worker()], start, 180)
    session = service.active[10]
    service.update_scene(
        [customer()],
        [worker(zones={"medicine_shelf"}, box=(500, 100, 560, 240))],
        start + timedelta(seconds=10),
        180,
    )
    service.update_scene(
        [customer()],
        [worker(zones={"employee_area"}, box=(360, 100, 420, 240))],
        start + timedelta(seconds=25),
        180,
    )
    assert session.current_phase == "RETURNING_TO_CUSTOMER"
    service.update_scene(
        [customer()], [worker()], start + timedelta(seconds=40), 180
    )
    finished = service.leave(10, start + timedelta(seconds=60))

    assert finished.service_seconds == 60
    assert finished.medicine_retrieval_seconds == 30
    assert finished.direct_interaction_seconds == 30


def test_worker_distance_alone_does_not_end_service_customer_departure_does():
    service = CustomerAnalyticsService(
        start_confirm_seconds=0,
        customer_lost_seconds=5,
        service_end_confirm_seconds=0,
        worker_return_seconds=120,
    )
    start = datetime(2026, 7, 25, tzinfo=UTC)
    service.update_scene([customer()], [worker()], start, 180)
    session = service.active[10]
    service.update_scene(
        [customer()],
        [worker(zones={"employee_area"}, box=(700, 100, 760, 240))],
        start + timedelta(seconds=20),
        180,
    )
    assert session.outcome == "ACTIVE"
    service.update_scene(
        [],
        [worker(zones={"employee_area"}, box=(700, 100, 760, 240))],
        start + timedelta(seconds=21),
        180,
    )
    service.advance(start + timedelta(seconds=26))
    assert session.outcome == "COMPLETED"
    assert session.service_ended_at == start + timedelta(seconds=20)


def test_retrieval_timeout_covers_fetching_and_return_walk_together():
    service = CustomerAnalyticsService(
        start_confirm_seconds=0,
        retrieval_timeout_seconds=20,
        worker_return_seconds=120,
    )
    start = datetime(2026, 7, 25, tzinfo=UTC)
    service.update_scene([customer()], [worker()], start, 180)
    session = service.active[10]
    service.update_scene(
        [customer()],
        [worker(zones={"medicine_shelf"}, box=(500, 100, 560, 240))],
        start + timedelta(seconds=5),
        180,
    )
    service.update_scene(
        [customer()],
        [worker(zones={"employee_area"}, box=(350, 100, 410, 240))],
        start + timedelta(seconds=15),
        180,
    )
    service.update_scene(
        [customer()],
        [worker(zones={"employee_area"}, box=(300, 100, 360, 240))],
        start + timedelta(seconds=26),
        180,
    )
    assert session.outcome == "INTERRUPTED"


def test_short_worker_gap_preserves_service_but_timeout_interrupts():
    start = datetime(2026, 7, 25, tzinfo=UTC)
    service = CustomerAnalyticsService(
        start_confirm_seconds=0,
        customer_lost_seconds=10,
        worker_return_seconds=5,
    )
    service.update_scene([customer()], [worker()], start, 180)
    session = service.active[10]
    service.update_scene([customer()], [], start + timedelta(seconds=3), 180)
    assert session.current_phase == "SERVING_AT_COUNTER"
    service.update_scene([customer()], [worker()], start + timedelta(seconds=4), 180)
    assert session.outcome == "ACTIVE"
    service.update_scene([customer()], [], start + timedelta(seconds=10), 180)
    assert session.outcome == "INTERRUPTED"


def test_one_worker_is_not_assigned_to_two_customers():
    start = datetime(2026, 7, 25, tzinfo=UTC)
    service = CustomerAnalyticsService(start_confirm_seconds=0)
    second = CustomerObservation(
        11, (110, 100, 170, 240), {"customer_area", "service_position"}, 0.9, 1
    )
    service.update_scene([customer(), second], [worker()], start, 180)
    sessions = list(service.active.values())
    assert sum(item.worker_session_id == "WS-1" for item in sessions) == 1
    assert sum(item.current_phase == "WAITING" for item in sessions) == 1


def test_customer_waiting_without_worker_and_lost_customer_abandons():
    start = datetime(2026, 7, 25, tzinfo=UTC)
    service = CustomerAnalyticsService(
        start_confirm_seconds=0, customer_lost_seconds=5
    )
    service.update_scene([customer()], [], start, 180)
    service.update_scene([customer()], [], start + timedelta(seconds=10), 180)
    service.update_scene([], [], start + timedelta(seconds=11), 180)
    service.advance(start + timedelta(seconds=16))
    finished = service.completed_sessions[-1]
    assert finished.outcome == "ABANDONED"
    assert finished.waiting_seconds == 10


def test_short_customer_track_change_reuses_the_same_journey(monkeypatch):
    monkeypatch.setattr(
        "services.customer_analytics.settings.customer_short_gap_relink_seconds", 6.0
    )
    start = datetime(2026, 7, 25, tzinfo=UTC)
    service = CustomerAnalyticsService(start_confirm_seconds=0)
    first = service.observe_customer(
        10, 1, start, (100, 100, 160, 240), {"waiting"}, 0.9
    )
    service.mark_customer_missing(10, start + timedelta(seconds=1))
    replacement = service.observe_customer(
        44,
        1,
        start + timedelta(seconds=5),
        (106, 100, 166, 240),
        {"waiting"},
        0.9,
    )
    assert replacement is first
    assert replacement.service_session_id == first.service_session_id
    assert replacement.original_track_ids == [10, 44]
    assert 10 not in service.active and service.active[44] is first


def test_legacy_abandoned_customer_is_included_in_manager_metrics():
    legacy = SimpleNamespace(
        waiting_seconds=61,
        service_seconds=None,
        medicine_retrieval_seconds=0,
        service_started_at=None,
        current_phase="WAITING",
        outcome="ACTIVE",
        completed=False,
        left_without_service=True,
        last_customer_seen_at=None,
    )
    assert customer_metrics([legacy])["abandoned_customers"] == 1
