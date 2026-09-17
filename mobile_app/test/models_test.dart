import 'package:flutter_test/flutter_test.dart';
import 'package:pharmacy_worker_monitor_v2/models/camera_model.dart';
import 'package:pharmacy_worker_monitor_v2/models/event_model.dart';
import 'package:pharmacy_worker_monitor_v2/models/worker_model.dart';
import 'package:pharmacy_worker_monitor_v2/models/live_person_model.dart';
import 'package:pharmacy_worker_monitor_v2/providers/camera_provider.dart';
import 'package:pharmacy_worker_monitor_v2/services/api_service.dart';

void main() {
  test('models tolerate nullable and missing backend fields', () {
    final camera = CameraModel.fromJson({'id': 1});
    final worker = WorkerModel.fromJson({'id': 'WS-1'});
    final event = EventModel.fromJson({'id': 'EV-1'});
    expect(camera.name, 'Unnamed camera');
    expect(worker.firstSeen, isNull);
    expect(event.activity, 'UNKNOWN');
  });

  test('live person includes explainable role and activity evidence', () {
    final person = LivePersonModel.fromJson({
      'track_id': 7,
      'role': 'WORKER',
      'activity': 'UNKNOWN',
      'evidence_status': 'INSUFFICIENT_EVIDENCE',
      'motion': 'STATIONARY',
      'stationary_seconds': 3.2,
      'candidate_activity': 'IDLE_CANDIDATE',
      'candidate_duration_seconds': 8.5,
      'idle_confirmation_seconds': 15,
      'track_age_seconds': 22,
      'track_stable': true,
      'evidence_quality': 'MEDIUM',
      'body_motion': 0.01,
      'pose_status': 'TEMPORARILY_MISSING',
      'idle_blocking_reasons': ['possible-phone evidence requires review'],
      'reasons': ['no camera zones configured'],
    });

    expect(person.trackId, 7);
    expect(person.role, 'WORKER');
    expect(person.evidenceStatus, 'INSUFFICIENT_EVIDENCE');
    expect(person.motion, 'STATIONARY');
    expect(person.stationarySeconds, 3.2);
    expect(person.candidateActivity, 'IDLE_CANDIDATE');
    expect(person.candidateDurationSeconds, 8.5);
    expect(person.idleConfirmationSeconds, 15);
    expect(person.trackStable, isTrue);
    expect(person.evidenceQuality, 'MEDIUM');
    expect(person.idleBlockingReasons, hasLength(1));
    expect(person.reasons, contains('no camera zones configured'));
  });

  test('camera provider applies live observed people from websocket', () {
    final provider = CameraProvider(ApiService(baseUrl: 'http://localhost'));

    provider.applyLive(4, {
      'observed_people': [
        {
          'track_id': 3,
          'display_name': 'Worker 1',
          'role': 'WORKER',
          'activity': 'SHELF_WORK',
          'confidence': 0.8,
          'reasons': ['zones: shelf_interaction'],
        },
      ],
    });

    expect(provider.livePeople[4], hasLength(1));
    expect(provider.livePeople[4]!.single.activity, 'SHELF_WORK');
  });
}
