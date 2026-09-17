from services.person_detector import (
    PersonObservation,
    merge_role_observations,
    valid_tracking_observation,
)


def test_lab_coat_evidence_is_merged_into_enclosing_person():
    values = merge_role_observations([
        PersonObservation((0, 0, 100, 200), 0.8, "person"),
        PersonObservation((10, 50, 90, 140), 0.7, "lab_coat"),
    ])

    assert len(values) == 1
    assert values[0].bbox == (0, 0, 100, 200)
    assert values[0].class_name == "lab_coat"


def test_unmatched_lab_coat_remains_a_detection():
    values = merge_role_observations([
        PersonObservation((0, 0, 20, 20), 0.8, "person"),
        PersonObservation((100, 100, 150, 180), 0.7, "lab_coat"),
    ])

    assert len(values) == 2


def test_duplicate_coat_boxes_do_not_create_duplicate_people():
    values = merge_role_observations(
        [
            PersonObservation((0, 0, 100, 200), 0.8, "person"),
            PersonObservation((10, 45, 90, 140), 0.7, "lab_coat"),
            PersonObservation((12, 47, 88, 138), 0.6, "lab_coat"),
        ]
    )

    assert len(values) == 1
    assert values[0].class_name == "lab_coat"


def test_isolated_verifier_coat_does_not_become_a_person_track():
    values = merge_role_observations(
        [PersonObservation((20, 30, 70, 100), 0.8, "lab_coat", "verifier")]
    )

    assert values == []


def test_verifier_coat_can_confirm_an_existing_person_box():
    values = merge_role_observations(
        [
            PersonObservation((0, 0, 100, 200), 0.7, "person"),
            PersonObservation((15, 45, 85, 140), 0.8, "lab_coat", "verifier"),
        ]
    )

    assert len(values) == 1
    assert values[0].bbox == (0, 0, 100, 200)
    assert values[0].class_name == "lab_coat"


def test_tiny_or_malformed_boxes_are_filtered_before_tracking():
    assert not valid_tracking_observation(
        PersonObservation((10, 10, 18, 32), 0.9, "person"), 960, 1080
    )
    assert valid_tracking_observation(
        PersonObservation((10, 10, 70, 160), 0.9, "person"), 960, 1080
    )
