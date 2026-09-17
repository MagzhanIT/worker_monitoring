from services.role_classifier import TemporalRoleClassifier


def classify(classifier: TemporalRoleClassifier, **evidence) -> str:
    result = "UNKNOWN"
    for _ in range(classifier.minimum_votes):
        result = classifier.update(7, **evidence)
    return result


def test_employee_floor_plus_shelf_hand_evidence_confirms_worker():
    classifier = TemporalRoleClassifier(window=5, minimum_votes=3)

    assert classify(
        classifier,
        employee_zone=True,
        worker_activity_zone=True,
    ) == "WORKER"


def test_shelf_interaction_alone_does_not_identify_worker():
    classifier = TemporalRoleClassifier(window=5, minimum_votes=3)

    assert classify(classifier, worker_activity_zone=True) == "UNKNOWN"


def test_customer_area_without_worker_evidence_confirms_customer():
    classifier = TemporalRoleClassifier(window=5, minimum_votes=3)

    assert classify(classifier, customer_zone=True) == "CUSTOMER"


def test_confirmed_worker_is_not_demoted_when_coat_is_temporarily_missed():
    classifier = TemporalRoleClassifier(
        window=5, minimum_votes=3, worker_promotion_hits=2
    )
    assert classifier.update(9, lab_coat_overlap=True) == "UNKNOWN"
    assert classifier.update(9, lab_coat_overlap=True) == "WORKER"

    for _ in range(8):
        assert classifier.update(9, customer_zone=True) == "WORKER"


def test_customer_track_can_only_promote_after_repeated_worker_evidence():
    classifier = TemporalRoleClassifier(
        window=7, minimum_votes=3, worker_promotion_hits=2
    )
    assert classify(classifier, customer_zone=True) == "CUSTOMER"
    assert classifier.update(7, lab_coat_overlap=True) == "CUSTOMER"
    assert classifier.update(7, lab_coat_overlap=True) == "WORKER"
