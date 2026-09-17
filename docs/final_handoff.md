# Pharmacy Worker Monitor V2 — final handoff

## 1. Architecture implemented

The project implements a **layered, event-driven computer-vision architecture with temporal evidence fusion and state-machine-based pharmacy operations analytics**:

camera source → independent capture → one-slot latest-frame buffer → scheduled person/role perception → stable track IDs → anonymous worker/customer sessions → pose/phone/zone evidence → temporally confirmed activity state → completed interval events → SQLite analytics/review/reporting → authenticated FastAPI/WebSocket → Flutter manager interface.

Camera unavailability closes active observed intervals, records a health period, publishes `UNKNOWN`/`CAMERA_UNAVAILABLE`, and splits anonymous sessions after continuity is lost. It is never converted to idle or absence.

## 2. Project tree

Generated Android/iOS/Web platform internals and ignored local environments/build caches are summarized; all authored application source is shown.

```text
pharmacy_worker_monitor_v2/
├── README.md
├── .gitignore
├── .env.example
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── SETUP_MAC.command
├── START_BACKEND_MAC.command
├── SETUP_WINDOWS_DOUBLE_CLICK.bat
├── START_BACKEND_WINDOWS.bat
├── FIX_WINDOWS_AI_TORCH.bat
├── FIX_WINDOWS_CAMERA_OPENCV.bat
├── backend/
│   ├── app.py, config.py, database.py, run_backend.py, logging_config.py
│   ├── requirements.txt, alembic.ini, pytest.ini
│   ├── api/
│   │   ├── auth.py, cameras.py, zones.py, workers.py, events.py
│   │   ├── reports.py, reviews.py, analytics.py, system.py, media.py
│   ├── db_models/
│   │   ├── user.py, camera.py, zone.py, camera_session.py
│   │   ├── worker_session.py, worker_snapshot.py, activity_event.py
│   │   ├── event_review.py, health_event.py, customer_session.py, daily_summary.py
│   ├── schemas/
│   │   ├── auth.py, camera.py, zone.py, worker.py, event.py
│   │   ├── report.py, review.py, analytics.py
│   ├── services/
│   │   ├── camera_manager.py, capture_service.py, source_parser.py, frame_buffer.py
│   │   ├── processing_service.py, model_registry.py, person_detector.py
│   │   ├── role_classifier.py, tracker.py, worker_session_service.py
│   │   ├── pose_service.py, phone_detector.py, phone_association.py
│   │   ├── zone_service.py, evidence_service.py, activity_engine.py
│   │   ├── state_machine.py, event_service.py, snapshot_service.py
│   │   ├── evidence_clip_service.py, customer_analytics.py, health_service.py
│   │   ├── analytics_service.py, report_service.py, sheets_service.py
│   │   ├── retention_service.py, session_manifest_service.py
│   ├── utilities/
│   │   ├── geometry.py, image_quality.py, time_utils.py, file_security.py, validation.py
│   ├── models/README.md
│   ├── storage/{worker_monitor.db,manifests/}
│   ├── reports/, evidence/, worker_snapshots/, debug_phone_misses/
│   ├── demo/README.md
│   ├── migrations/README.md
│   └── tests/
│       ├── conftest.py, test_api.py, test_sources.py, test_zones.py
│       ├── test_tracker.py, test_worker_sessions.py, test_pose.py, test_phone.py
│       ├── test_activity_engine.py, test_events.py, test_snapshots.py
│       ├── test_customer_analytics.py, test_camera_health.py
│       ├── test_reports.py, test_security.py, test_retention.py
├── mobile_app/
│   ├── pubspec.yaml, analysis_options.yaml, README.md
│   ├── android/ (generated Flutter Android shell)
│   ├── ios/ (generated Flutter iOS shell)
│   ├── web/ (generated Flutter Web shell)
│   ├── assets/
│   ├── lib/
│   │   ├── main.dart
│   │   ├── config/app_config.dart
│   │   ├── models/{camera_model,worker_model,event_model,zone_model,report_model,health_model}.dart
│   │   ├── services/{api_service,auth_service,websocket_service,report_service}.dart
│   │   ├── providers/{auth_provider,camera_provider,report_provider,settings_provider}.dart
│   │   ├── screens/{login_screen,dashboard_screen,camera_detail_screen}.dart
│   │   ├── screens/{zone_editor_screen,worker_sessions_screen,worker_session_detail_screen}.dart
│   │   ├── screens/{event_review_screen,daily_report_screen,system_health_screen,settings_screen}.dart
│   │   ├── widgets/{camera_stream,worker_row,worker_session_card,activity_badge}.dart
│   │   ├── widgets/{health_badge,zone_painter,event_card,report_metric}.dart
│   │   └── theme/app_theme.dart
│   └── test/{models_test.dart,zone_mapping_test.dart}
└── docs/
    ├── architecture.md, dataflow.md, state_machine.md, database.md, zones.md
    ├── pose.md, phone_detection.md, anonymous_worker_sessions.md, snapshots.md
    ├── customer_analytics.md, reporting.md, privacy.md, security.md
    ├── testing.md, evaluation.md, limitations.md, model_registry.md
    ├── mac_setup.md, windows_setup.md, commercial_pilot.md, final_handoff.md
```

## 3. Backend features

- Typed environment configuration, SQLite/SQLAlchemy schema and version table.
- Bcrypt passwords, signed expiring JWTs, manager/admin authorization, CORS configuration, protected media, safe relative paths and RTSP credential redaction/encryption at rest.
- `rtsp://`, `rtsps://`, `file://`, Windows file URLs, `webcam://` and looping `demo://sample` parsing.
- Independent reconnecting reader with a single newest-frame slot; no unbounded frame queue.
- Health states and counters for advancing sequence, age, decode failures, reconnects, FPS and model availability. Advancing static frames remain healthy.
- Dynamic YOLO class discovery, conservative temporal role votes, stable IoU/centre-distance tracks and anonymous continuous sessions.
- Camera-specific normalized polygon validation/membership with temporal edge confirmation.
- Exact pose crop/global coordinate records, confidence decay, missing-frame hold, stale expiry, jump/outside/bone rejection and same-track smoothing.
- Periodic full-worker phone search plus immediate focused upper-body/wrist search; one-to-one association diagnostics; physical/behavior class separation; two-of-five physical confirmation; release after misses.
- One official activity from prioritized temporal evidence; `POSSIBLE_PHONE`, `POSSIBLE_IDLE`, `UNKNOWN` and `CAMERA_UNAVAILABLE` stay separate.
- Interval events, local evidence clips around important transitions, worker-only quality-ranked face/body reference crops, anonymous customer waiting/service sessions and retention cleanup.
- Manager review preserves original activity/confidence and stores a separate decision.
- Daily analytics, report-quality fields, CSV history, manager HTML, optional aggregate-only Google Sheets upload and local success when Sheets fails.
- Per-camera session manifests with configuration, zones, model hashes/status, repository state, FPS, reconnects, unavailable time and output paths.

## 4. Flutter features

- Responsive Material 3 login and manager navigation for Web, iOS and Android.
- Overview metrics, cameras, live MJPEG, start/stop/restart, health/FPS, anonymous worker rows and WebSocket reconnect.
- Exact-frame normalized zone editor with `BoxFit.contain` letterbox reversal, add/undo/reset/close, formal zone type, validation, save and delete.
- Anonymous worker-session list/detail with optional protected face/body references and a clear identity-disabled notice.
- Important event review for confirmed/false alarm/approved/unclear decisions without overwriting the original.
- Daily reports, customer-service metrics, quality/unavailable fields, system health and normal/debug preference.
- Nullable/missing API fields and API errors are handled conservatively.

## 5. Database schema

Tables: `users`, `cameras`, `camera_zones`, `camera_sessions`, `worker_sessions`, `worker_snapshots`, `activity_events`, `event_reviews`, `system_health_events`, `customer_sessions`, `daily_summaries`, `schema_versions`.

Important identifiers remain separate: `camera_id`, `camera_session_id`, `track_id`, `worker_session_id`, `event_id`, `service_session_id`. `employee_id` is nullable and never assigned by this version. Media is stored as file paths, never database blobs.

## 6. API and WebSocket

```text
POST /auth/login                     GET /auth/me
GET  /health                         GET /system/status
GET|POST /cameras                    GET|PUT|DELETE /cameras/{camera_id}
POST /cameras/{id}/start|stop|restart
GET  /cameras/{id}/status|frame.jpg|stream.mjpeg
GET|POST /cameras/{id}/zones
POST /cameras/{id}/zones/validate
PUT|DELETE /cameras/{id}/zones/{zone_id}
GET  /worker-sessions                GET /worker-sessions/{session_id}
GET  /worker-sessions/{id}/events|snapshots
GET  /events                         GET /events/{event_id}
POST /events/{event_id}/review
GET  /analytics/daily                GET /analytics/customer-service
POST /reports/generate               GET /reports/latest
GET  /reports/latest/download        GET /reports/latest/events/download
GET  /reports/latest/manager-html
GET  /media/snapshots/{safe_id}       GET /media/evidence/{safe_id}
WS   /ws/cameras/{camera_id}?token={signed_access_token}
```

## 7. Expected local models

| Purpose | Path | Expected classes/data |
|---|---|---|
| Person/role detector | `backend/models/employee_customer.pt` | `person`, optionally `lab_coat` |
| Phone detector | `backend/models/phone_yolo.pt` | physical phone names and/or `phone_call` behavior |
| Pose | `backend/models/yolo11n-pose.pt` | COCO-17 keypoints |
| Optional crop-only face detector | `backend/models/optional_face_detector.onnx` | OpenCV YuNet-compatible face boxes |

Weights are intentionally absent, ignored by Git and never downloaded at runtime. Missing weights produce explicit unavailable status while auth, cameras, health, zones and reports continue.

## 8. Configuration variables

The exact runnable template is `.env.example`. Groups:

- Application/security: `APP_NAME`, `APP_ENV`, `APP_RELOAD`, `APP_HOST`, `APP_PORT`, `APP_SECRET_KEY`, `DATABASE_URL`, `CORS_ORIGINS`, `DEFAULT_ADMIN_USERNAME`, `DEFAULT_ADMIN_PASSWORD`, `ACCESS_TOKEN_MINUTES`.
- In `development`, browser frontends served from any `localhost` or `127.0.0.1` port are also accepted. This supports Flutter's dynamically selected web port without opening CORS to non-local hosts.
- Models/detection: `PERSON_MODEL_PATH`, `PHONE_MODEL_PATH`, `POSE_MODEL_PATH`, `WORKER_DETECTION_MODE`, `PERSON_CONFIDENCE`, `LAB_COAT_CONFIDENCE`.
- Tracking: `TRACK_IOU_THRESHOLD`, `TRACK_MAX_CENTER_DISTANCE`, `TRACK_MAX_MISSED_SECONDS`.
- Pose: `POSE_ENABLED`, `POSE_RUN_EVERY_N_FRAMES`, `POSE_IMGSZ`, `POSE_PERSON_CONFIDENCE`, `POSE_KEYPOINT_CONFIDENCE`, `POSE_MAX_STALE_SECONDS`, `POSE_HOLD_MISSING_UPDATES`, `POSE_CONFIDENCE_DECAY`, `POSE_SMOOTHING_ALPHA`.
- Phone: `PHONE_ENABLED`, periodic/focused cadence, crop sizes/expansions, threshold, confirm window/hits, release misses and memory variables.
- Zones/state: zone window/hits/memory/area limits, `STATE_SWITCH_CONFIRM_SECONDS`, `STATE_MIN_DURATION_SECONDS`, `POSSIBLE_IDLE_THRESHOLD_SECONDS`, `ABSENCE_THRESHOLD_SECONDS`.
- Evidence/snapshots/customers/health: clip pre/post, snapshot cadence/count/quality/face size, customer wait/service thresholds, freeze/reconnect thresholds.
- Retention/Sheets: snapshot/evidence/debug retention days and `GOOGLE_SHEETS_*` variables.

No secret is hardcoded. A default admin is created only when `DEFAULT_ADMIN_PASSWORD` is explicitly non-empty.

## 9. macOS setup

1. Use Python 3.11 or 3.12 and an installed Flutter SDK.
2. Copy `.env.example` to `.env`; set a unique `APP_SECRET_KEY` and an initial `DEFAULT_ADMIN_PASSWORD` if desired.
3. Add licensed model weights and an authorized `backend/demo/demo_source.mp4` when needed.
4. Double-click `SETUP_MAC.command`, then `START_BACKEND_MAC.command`.
5. In `mobile_app`, run `flutter run -d chrome`.

## 10. Windows setup

1. Install Python 3.11/3.12, Flutter and the Microsoft Visual C++ 2015–2022 x64 Redistributable.
2. Never copy a macOS virtual environment. Copy/edit `.env` and add licensed local weights.
3. Double-click `SETUP_WINDOWS_DOUBLE_CLICK.bat`, then `START_BACKEND_WINDOWS.bat`.
4. Use `FIX_WINDOWS_AI_TORCH.bat` for PyTorch/`c10.dll` repair and `FIX_WINDOWS_CAMERA_OPENCV.bat` for OpenCV repair.

The scripts invoke `backend\.venv\Scripts\python.exe` directly; PowerShell activation is unnecessary.

## 11–12. Validation commands and measured results

```text
backend/.venv/bin/python -m compileall -q .       PASS
backend/.venv/bin/python -m pytest -q              49 passed
full imports                                       PASS
  FastAPI 0.115.6, SQLAlchemy 2.0.36, OpenCV 4.10.0,
  Ultralytics 8.3.51, Torch 2.5.1, NumPy 1.26.4
backend live /health probe                          HTTP 200
dart analyze                                        No issues found!
flutter test                                        2 passed
flutter build web --release                         PASS
flutter run -d chrome                               PASS
desktop and 390×844 responsive render checks        PASS
local empty-data CSV/HTML report generation         PASS
```

Model inference accuracy was not measured because proprietary/trained weight files and authorized pharmacy footage were not supplied.

## 13. Example worker API response

```json
{
  "id": "WS-20260719-C1-a1b2c3-007",
  "camera_id": 1,
  "camera_session_id": "CS-20260719-91a1b2c3",
  "track_id": 7,
  "employee_id": null,
  "display_name": "Worker 1",
  "first_seen": "2026-07-19T09:00:00Z",
  "last_seen": "2026-07-19T09:41:00Z",
  "ended_at": null,
  "observed_seconds": 2460,
  "role_confidence": 0.84,
  "global_worker_id": "GW-20260719-A1B2C3",
  "identity_match_status": "appearance_matched",
  "identity_confidence": 0.86,
  "limitations_json": ["Anonymous day-scoped clothing/body association; no face recognition; manager review recommended."]
}
```

## 14. Example confirmed physical-phone event

```json
{
  "id": "EV-12c09a4f8a01a2e3",
  "worker_session_id": "WS-20260719-C1-a1b2c3-007",
  "track_id": 7,
  "presence": "VISIBLE",
  "activity": "ON_PHONE",
  "start_time": "2026-07-19T09:18:00Z",
  "end_time": "2026-07-19T09:22:00Z",
  "duration_seconds": 240,
  "confidence": 0.88,
  "reasons_json": ["associated physical phone confirmed in at least 2 of 5 checks"],
  "limitations_json": [],
  "review_status": "unreviewed"
}
```

## 15. Example possible-phone event

```json
{
  "id": "EV-62a9f214bb01cc83",
  "worker_session_id": "WS-20260719-C1-a1b2c3-007",
  "presence": "VISIBLE",
  "activity": "POSSIBLE_PHONE",
  "duration_seconds": 14,
  "confidence": 0.53,
  "reasons_json": ["persistent phone-like pose; focused search active"],
  "limitations_json": ["physical phone object was not confirmed"],
  "review_status": "unreviewed"
}
```

`phone_call` behavior or pose alone can create this result but can never create `ON_PHONE`.

## 16. Example anonymous customer-service session

```json
{
  "id": "CSVC-20260719-0003",
  "customer_track_id": 21,
  "worker_session_id": "WS-20260719-C1-a1b2c3-007",
  "camera_id": 1,
  "waiting_started_at": "2026-07-19T10:04:00Z",
  "service_started_at": "2026-07-19T10:04:32Z",
  "service_ended_at": "2026-07-19T10:06:05Z",
  "waiting_seconds": 32,
  "service_seconds": 93,
  "completed": true,
  "left_without_service": false,
  "confidence": 0.81
}
```

## 17. Example manager report

The generated local example is `backend/reports/latest_manager_report.html`. It contains the ten requested sections, honest unavailable values for missing observations, anonymous session cards, separate confirmed/possible totals, original/reviewed status, limitations and privacy notice. Companion files are `latest_report.csv`, `latest_events.csv` and `latest_customer_report.csv`, with timestamped history copies.

## 18. Face recognition confirmation

**No face recognition, face embeddings, face comparison, employee face gallery, automatic employee naming or cross-session face merging was added.** The optional ONNX path is used only to return candidate crop boxes for authorized manager visual reference. Customer face snapshots are never deliberately captured.

## 19. Current maturity

| Area | Implemented | Tested/measured | Maturity |
|---|---|---|---|
| Config, DB, auth, protected media/API | Yes | Unit/API + live health probe | Working reference |
| Source parsing, capture, reconnect, health | Yes | Synthetic tests; no supplied live RTSP | Prototype |
| Tracking, anonymous sessions, zones | Yes | Synthetic temporal/geometry tests | Prototype |
| Pose/phone/activity pipeline | Yes | Logic/import tests; no site weights/data | Prototype, accuracy unmeasured |
| Interval events, reviews, reports, retention | Yes | Automated + local generation | Working reference |
| Flutter Web/iOS/Android manager UI | Yes | Analyze, tests, Web build, Chrome render | Student prototype |
| Real-pharmacy accuracy/reliability | Not yet | Not measured | Pre-pilot |

## 20. Known limitations

- Small phones may be invisible from overhead cameras; physical confirmation can therefore remain unavailable.
- Pose is degraded by occlusion and crowding.
- Anonymous track loss can split one real worker into several sessions; they are deliberately not merged.
- Face crops are visual references, not identity recognition.
- Camera coverage does not equal complete knowledge of work, and subtle reading/hand work may remain `UNKNOWN`.
- Zone quality and camera placement strongly affect cashier/shelf/service events.
- Evidence clips are bounded review samples around important transitions, not a complete video archive.
- The reference IoU/centre tracker is understandable and tested but should be benchmarked against ByteTrack for crowded real footage.
- iOS/Android device behavior and RTSP hardware were not tested in this workstation validation.
- Real accuracy, fairness, latency, storage growth and operational failure behavior are not yet measured.

## 21. Remaining work before a pharmacy pilot

Obtain privacy/legal approval and notices; set access/retention policy; supply licensed models; calibrate every camera and zones; collect consented representative evaluation footage; measure per-class and interval precision/recall, wait-time error, unknown coverage, FPS and p95 latency; compare tracker choices; test night/glare/occlusion/crowding; conduct security review; add backup/monitoring/incident response; test Windows/macOS/mobile devices and actual RTSP hardware; train managers on review limitations; and run a reversible shadow pilot with no employment or salary consequences.
