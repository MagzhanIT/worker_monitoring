from services.tracker import Detection, StableTracker


def test_stable_track_matching_and_short_missing_detection():
    tracker = StableTracker(iou_threshold=0.1, max_distance=100, max_missed=2)
    first, _ = tracker.update([Detection((0, 0, 100, 100), 0.9)], 0)
    second, _ = tracker.update([Detection((4, 0, 104, 100), 0.8)], 1)
    assert first[0].track_id == second[0].track_id
    missing, expired = tracker.update([], 2)
    assert missing[0].predicted and not expired


def test_track_expiration_and_no_cross_track_history_transfer():
    tracker = StableTracker(iou_threshold=0.2, max_distance=20, max_missed=1)
    original, _ = tracker.update([Detection((0, 0, 10, 10), 0.9)], 0)
    _, expired = tracker.update([], 2)
    replacement, _ = tracker.update([Detection((100, 100, 110, 110), 0.9)], 3)
    assert expired[0].track_id == original[0].track_id
    assert replacement[0].track_id != original[0].track_id


def test_tracking_uses_ids_not_detection_order():
    tracker = StableTracker(iou_threshold=0.1, max_distance=40, max_missed=2)
    first, _ = tracker.update([Detection((0, 0, 20, 20), 0.9), Detection((100, 0, 120, 20), 0.8)], 0)
    second, _ = tracker.update([Detection((102, 0, 122, 20), 0.8), Detection((2, 0, 22, 20), 0.9)], 1)
    assert {track.track_id: track.bbox[0] < 50 for track in first} == {track.track_id: track.bbox[0] < 50 for track in second}


def test_velocity_prediction_recovers_id_after_a_short_detection_gap():
    tracker = StableTracker(iou_threshold=0.2, max_distance=25, max_missed=3)
    original, _ = tracker.update([Detection((0, 0, 20, 40), 0.9)], 0)
    tracker.update([Detection((20, 0, 40, 40), 0.9)], 1)
    predicted, _ = tracker.update([], 2)

    assert predicted[0].predicted
    recovered, _ = tracker.update([Detection((50, 0, 70, 40), 0.9)], 3)
    assert recovered[0].track_id == original[0].track_id


def test_track_requires_consecutive_hits_before_confirmation():
    tracker = StableTracker(iou_threshold=0.1, max_distance=50, max_missed=2)
    first, _ = tracker.update([Detection((0, 0, 30, 80), 0.9)], 0)
    assert not first[0].confirmed

    second, _ = tracker.update([Detection((2, 0, 32, 80), 0.9)], 1)
    assert second[0].confirmed


def test_unconfirmed_track_does_not_confirm_across_a_missing_frame():
    tracker = StableTracker(iou_threshold=0.1, max_distance=50, max_missed=2)
    tracker.update([Detection((0, 0, 30, 80), 0.9)], 0)
    tracker.update([], 1)
    returned, _ = tracker.update([Detection((2, 0, 32, 80), 0.9)], 2)
    assert not returned[0].confirmed
