from services.activity_engine import PhoneTemporalHistory
from services.phone_association import associate_phones
from services.phone_detector import PhoneCandidate, PhoneSearchScheduler, inspect_phone_classes


def test_phone_class_discovery_and_behavior_separation():
    assert inspect_phone_classes(["person", "phone"]) == "PHYSICAL_PHONE_MODEL"
    assert inspect_phone_classes(["phone_call"]) == "PHONE_BEHAVIOUR_MODEL"
    assert inspect_phone_classes(["phone", "phone_call"]) == "MIXED_PHONE_MODEL"


def test_periodic_and_focused_search_without_duplicates():
    scheduler = PhoneSearchScheduler()
    scheduler.begin_frame()
    assert scheduler.should_search(7, 4, "person", 1.0)
    assert not scheduler.should_search(7, 4, "person", 1.0)
    scheduler.trigger_focused(7, 1.0)
    scheduler.begin_frame()
    assert scheduler.should_search(7, 5, "left_wrist", 1.1)


def test_wrist_association_and_phone_on_shelf_rejected():
    candidate = PhoneCandidate((40, 40, 50, 55), 0.8, "phone", "person")
    people = [{"track_id": 7, "bbox": (0, 0, 100, 200), "wrists": {"left": (45, 50)}}]
    result = associate_phones([candidate], people)[0]
    assert result.track_id == 7 and result.phone_near_left_wrist
    shelf = PhoneCandidate((300, 300, 320, 330), 0.9, "phone", "full_frame")
    assert associate_phones([shelf], people)[0].association_status == "REJECTED"


def test_low_confidence_crop_phone_requires_pose_geometry():
    candidate = PhoneCandidate((40, 40, 50, 55), 0.012, "cell phone", "upper_body")
    far_wrist = [{"track_id": 7, "bbox": (0, 0, 100, 200), "wrists": {"left": (90, 170)}}]
    assert associate_phones([candidate], far_wrist)[0].association_status == "REJECTED"
    near_wrist = [{"track_id": 7, "bbox": (0, 0, 100, 200), "wrists": {"left": (45, 50)}}]
    assert associate_phones([candidate], near_wrist)[0].association_status == "ASSOCIATED"


def test_wrist_crop_uses_lower_proposal_threshold_but_no_pose_fallback_is_strict():
    wrist_candidate = PhoneCandidate((40, 40, 50, 55), 0.003, "cell phone", "left_wrist")
    near_wrist = [{"track_id": 7, "bbox": (0, 0, 100, 200), "wrists": {"left": (45, 50)}}]
    assert associate_phones([wrist_candidate], near_wrist)[0].association_status == "ASSOCIATED"
    no_pose = [{"track_id": 7, "bbox": (0, 0, 100, 200), "wrists": {}}]
    assert associate_phones([wrist_candidate], no_pose)[0].association_status == "REJECTED"


def test_phone_behavior_needs_person_overlap_and_hand_near_face():
    candidate = PhoneCandidate((0, 0, 100, 200), 0.8, "phone_call", "person")
    accepted = [{"track_id": 7, "bbox": (0, 0, 100, 200), "wrists": {"left": (48, 45)}, "face": (50, 35)}]
    assert associate_phones([candidate], accepted)[0].association_status == "ASSOCIATED"
    rejected = [{"track_id": 7, "bbox": (0, 0, 100, 200), "wrists": {"left": (50, 180)}, "face": (50, 35)}]
    assert associate_phones([candidate], rejected)[0].association_status == "REJECTED"


def test_one_hit_does_not_confirm_two_of_five_does_and_misses_release():
    history = PhoneTemporalHistory(window=5, min_hits=2, release_misses=3)
    assert history.update(7, True) == "POSSIBLE_PHONE"
    assert history.update(7, False) == "POSSIBLE_PHONE"
    assert history.update(7, True) == "ON_PHONE"
    assert history.update(7, False) == "ON_PHONE"
    assert history.update(7, False) == "ON_PHONE"
    assert history.update(7, False) != "ON_PHONE"


def test_track_expiry_clears_phone_state():
    history = PhoneTemporalHistory(window=5, min_hits=2, release_misses=3)
    history.update(7, True); history.update(7, True)
    history.clear(7)
    assert 7 not in history.confirmed and 7 not in history.hits


def test_phone_time_confirmation_and_hold_are_separate_from_possible(monkeypatch):
    monkeypatch.setattr("services.activity_engine.settings.phone_confirm_seconds", 0.6)
    monkeypatch.setattr("services.activity_engine.settings.phone_hold_seconds", 1.5)
    history = PhoneTemporalHistory(window=5, min_hits=2, release_misses=1)
    assert history.update(9, True, 0.0) == "POSSIBLE_PHONE"
    assert history.update(9, True, 0.2) == "POSSIBLE_PHONE"
    assert history.update(9, True, 0.7) == "ON_PHONE"
    assert history.update(9, False, 1.0) == "ON_PHONE"
    assert history.update(9, False, 2.3) != "ON_PHONE"
