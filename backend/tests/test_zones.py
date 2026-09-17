from services.zone_service import TemporalZoneHistory, memberships, validate_zone
from utilities.geometry import normalized_to_pixel, screen_to_normalized


def test_normalized_to_pixel_conversion():
    assert normalized_to_pixel([(0.5, 0.25)], 1920, 1080) == [(960, 270)]


def test_letterbox_coordinate_conversion():
    # 16:9 image in square view leaves top/bottom letterboxing.
    assert screen_to_normalized((500, 500), (1000, 1000), (1920, 1080)) == (0.5, 0.5)
    assert screen_to_normalized((500, 100), (1000, 1000), (1920, 1080)) is None


def test_self_intersection_rejected():
    valid, errors, _ = validate_zone([(0.1, 0.1), (0.9, 0.9), (0.1, 0.9), (0.9, 0.1)])
    assert not valid
    assert any("self-intersect" in error for error in errors)


def test_membership_and_overlapping_priority():
    zones = [
        {"zone_type": "employee_area", "normalized_points": [(0, 0), (1, 0), (1, 1), (0, 1)]},
        {"zone_type": "cashier", "normalized_points": [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]},
    ]
    all_zones, primary = memberships((0.5, 0.5), zones)
    assert all_zones == ["cashier", "employee_area"]
    assert primary == "cashier"


def test_temporal_zone_confirmation_is_track_keyed():
    history = TemporalZoneHistory(window=3, hits=2)
    assert not history.update(7, {"cashier"})
    assert history.update(7, {"cashier"}) == {"cashier"}
    assert history.update(8, set()) == set()

