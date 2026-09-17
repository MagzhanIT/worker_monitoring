from datetime import UTC, datetime, timedelta

from services.customer_analytics import CustomerAnalyticsService, customer_metrics


def test_waiting_service_and_completion():
    service = CustomerAnalyticsService()
    now = datetime(2026, 7, 19, tzinfo=UTC)
    session = service.waiting(21, 1, now)
    service.begin_service(21, "WS-1", now + timedelta(seconds=30), 0.8)
    finished = service.leave(21, now + timedelta(seconds=90))
    assert session.service_session_id.startswith("CSVC-")
    assert finished.waiting_seconds == 30 and finished.service_seconds == 60 and finished.completed


def test_left_without_service_and_no_face_fields():
    service = CustomerAnalyticsService()
    now = datetime(2026, 7, 19, tzinfo=UTC)
    service.waiting(21, 1, now)
    finished = service.leave(21, now + timedelta(seconds=20))
    assert finished.left_without_service and not hasattr(finished, "face_snapshot")
    assert customer_metrics([finished])["customers_left_without_service"] == 1

