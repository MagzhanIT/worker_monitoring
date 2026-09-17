from pathlib import Path

import numpy as np

from offline_video_test import (
    SummaryCollector,
    build_parser,
    default_artifact_paths,
    default_json_path,
    default_output_path,
    evaluate_ground_truth,
    format_seconds,
    status_text,
)
from services.offline_worker_dataset import OfflineWorkerDatasetExporter


def test_default_artifact_paths_do_not_overwrite_input():
    source = Path("C:/videos/shop.test.mp4")
    output = default_output_path(source)
    assert output == Path("C:/videos/shop.test_backend_test.mp4")
    assert output != source
    assert default_json_path(output) == Path("C:/videos/shop.test_backend_test.json")
    artifacts = default_artifact_paths(output)
    assert artifacts["events_csv"].name == "shop.test_backend_test_events.csv"
    assert artifacts["diagnostics_csv"].name == "shop.test_backend_test_diagnostics.csv"
    assert artifacts["customers_csv"].name == "shop.test_backend_test_customers.csv"
    assert artifacts["manager_html"].name == "shop.test_backend_test_manager.html"


def test_manager_facing_status_text_is_evidence_oriented():
    assert status_text("WORK_OBSERVED") == "Work observed"
    assert status_text("REVIEW_NEEDED") == "Review needed"
    assert status_text("CUSTOMER_OBSERVED") == "Customer observed"
    assert status_text("INSUFFICIENT_EVIDENCE") == "Insufficient evidence"


def test_format_seconds_supports_long_videos():
    assert format_seconds(0) == "00:00:00"
    assert format_seconds(3661) == "01:01:01"


def test_summary_collector_accumulates_anonymous_track_evidence():
    collector = SummaryCollector()
    observation = {
        "track_id": 7,
        "role": "WORKER",
        "activity": "SHELF_WORK",
        "evidence_status": "WORK_OBSERVED",
        "zone": "shelf_interaction",
        "confidence": 0.8,
        "phone_evidence": "No phone evidence",
    }
    collector.update([observation], 1.0, 0.5)
    collector.update([observation], 1.5, 0.5)
    result = collector.as_dict()
    assert result["unique_track_ids"] == 1
    assert result["evidence_status_seconds"] == {"WORK_OBSERVED": 1.0}
    assert result["tracks"][0]["observed_seconds"] == 1.0
    assert result["tracks"][0]["zones"] == {"shelf_interaction": 2}
    assert result["phone_evidence_seconds"] == {"No phone evidence": 1.0}


def test_summary_relinks_changed_track_id_to_same_worker_session():
    collector = SummaryCollector()
    base = {
        "role": "WORKER",
        "activity": "SERVING_CUSTOMER",
        "evidence_status": "WORK_OBSERVED",
        "zone": "service_position",
        "confidence": 0.9,
        "phone_evidence": "No phone evidence",
        "worker_session_id": "WS-OFFLINE-1",
        "worker_label": "Worker 1",
    }
    collector.update([{**base, "track_id": 4}], 1.0, 0.5)
    collector.update([{**base, "track_id": 11}], 2.0, 0.5)

    result = collector.as_dict()
    assert result["unique_track_ids"] == 2
    assert result["unique_entities"] == 1
    assert result["anonymous_worker_sessions"] == 1
    assert result["tracks"][0]["track_ids"] == [4, 11]
    assert result["tracks"][0]["observed_seconds"] == 1.0


def test_worker_dataset_export_never_writes_customer_crop(tmp_path):
    exporter = OfflineWorkerDatasetExporter(
        tmp_path, "sample", every_frames=1, max_per_worker=2
    )
    frame = np.full((120, 160, 3), 128, dtype=np.uint8)
    shared = {
        "bbox": (10, 10, 70, 110),
        "confidence": 0.8,
        "reasons": ["test evidence"],
        "session_stitch": None,
    }
    saved = exporter.export(
        frame,
        1,
        0.1,
        [
            {
                **shared,
                "track_id": 1,
                "role": "WORKER",
                "worker_session_id": "WS-1",
            },
            {
                **shared,
                "track_id": 2,
                "role": "CUSTOMER",
                "worker_session_id": None,
            },
        ],
    )

    assert saved == 1
    summary = exporter.summary()
    assert summary["saved_worker_crops"] == 1
    assert summary["customers_exported"] == 0
    assert len(list((tmp_path / "sample" / "worker_identity_crops").rglob("*.jpg"))) == 1


def test_preview_cli_can_be_enabled_or_disabled_for_windows_batch():
    parser = build_parser()
    assert parser.parse_args(["video.mp4", "--preview"]).preview
    assert not parser.parse_args(["video.mp4", "--preview", "--no-preview"]).preview


def test_offline_idle_event_is_emitted_once_and_contains_auditable_evidence():
    collector = SummaryCollector()
    base = {
        "track_id": 7,
        "role": "WORKER",
        "worker_session_id": "WS-STABLE",
        "worker_label": "Worker 1",
        "activity": "IDLE",
        "evidence_status": "CONFIRMED_IDLE",
        "zone": "employee_area",
        "confidence": 0.9,
        "phone_evidence": "No phone evidence",
        "evidence_quality": "MEDIUM",
        "body_motion": 0.01,
        "wrist_motion": 0.0,
        "elbow_motion": 0.0,
    }
    collector.update([base], 35.0, 1.0)
    collector.update([base], 36.0, 1.0)
    collector.update(
        [
            {
                **base,
                "activity": "SHELF_WORK",
                "evidence_status": "WORK_OBSERVED",
                "body_motion": 0.2,
            }
        ],
        65.0,
        1.0,
    )
    collector.finalize(66.0)

    idle = [event for event in collector.events if event["activity"] == "IDLE"]
    assert len(idle) == 1
    assert idle[0]["transition_type"] == "IDLE_STARTED"
    assert idle[0]["end_transition_type"] == "IDLE_ENDED"
    assert idle[0]["duration_seconds"] == 30.0
    assert idle[0]["raw_track_ids"] == [7]
    assert idle[0]["evidence_quality"] == "MEDIUM"


def test_ground_truth_evaluation_is_deterministic_and_scores_idle():
    truth = [
        {
            "camera_id": 4,
            "worker_label": "Worker 1",
            "start_seconds": 35.0,
            "end_seconds": 65.0,
            "expected_activity": "IDLE",
            "notes": "controlled interval",
        }
    ]
    diagnostics = [
        {
            "timestamp_seconds": second,
            "worker_label": "Worker 1",
            "worker_session_id": "WS-1",
            "raw_track_id": 7,
            "role": "WORKER",
            "final_activity": "IDLE",
        }
        for second in range(35, 65)
    ]
    events = [
        {
            "event_id": "E-1",
            "worker_label": "Worker 1",
            "worker_session_id": "WS-1",
            "activity": "IDLE",
            "start_seconds": 35.0,
            "end_seconds": 65.0,
            "duration_seconds": 30.0,
        }
    ]
    first = evaluate_ground_truth(truth, diagnostics, events)
    second = evaluate_ground_truth(truth, diagnostics, events)
    assert first == second
    assert first["idle_precision"] == 1.0
    assert first["idle_recall"] == 1.0
    assert first["idle_f1"] == 1.0
    assert first["total_idle_duration_error_seconds"] == 0.0
    assert first["false_idle_count"] == first["missed_idle_count"] == 0


def test_validation_cli_accepts_zones_and_ground_truth_files():
    args = build_parser().parse_args(
        [
            "video.mp4",
            "--zones-json",
            "zones.json",
            "--ground-truth",
            "truth.csv",
        ]
    )
    assert args.zones_json == "zones.json"
    assert args.ground_truth == "truth.csv"
