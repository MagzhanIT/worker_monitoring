# Customer service, session continuity, and TEST mode

## Customer-service state machine

The camera-local customer manager uses these persisted phases:

`WAITING → SERVING_AT_COUNTER → FETCHING_MEDICINE → RETURNING_TO_CUSTOMER → SERVING_AT_COUNTER/COMPLETING_TRANSACTION → COMPLETED`

`ABANDONED` and `INTERRUPTED` are terminal alternatives. Temporary worker
distance, a short tracker gap, or medicine retrieval does not end total service.
One worker has at most one primary customer and one customer has at most one
primary worker. Reassignment is never inferred from weak evidence.

Waiting runs from entry into a configured queue/service area until assignment
confirmation. Total service runs from assignment confirmation until the final
outcome. Direct interaction, retrieval, and transaction intervals are reported
inside that total rather than as unrelated visits.

Medicine retrieval covers both `FETCHING_MEDICINE` and
`RETURNING_TO_CUSTOMER`, ending only when direct counter/POS interaction
resumes. This keeps the walk back from the shelf inside retrieval time and
prevents it from being misreported as direct customer interaction.

## Required zones

- `waiting`: customer queue floor; starts waiting measurement.
- `customer_area`: customer-accessible floor.
- `service_position`: worker/customer service position.
- `cashier`: staff floor behind the counter.
- `register_interaction`: register work surface.
- `medicine_shelf`: medicine shelf/drawer interaction surface.
- `shelf_interaction`: general shelf/restocking surface.
- `storage`: staff storage floor.
- `computer`: computer interaction surface.
- `pos`: payment-terminal interaction surface.
- `employee_area`: normal staff floor.

Draw floor zones under feet and interaction zones over the surface reached by
the worker's hands. Camera 4 had no enabled zones during the last offline smoke
test, so service and zone-specific work could not be established there.

## Configuration

- `SERVICE_START_CONFIRM_SECONDS`
- `SERVICE_LOST_GRACE_SECONDS`
- `MEDICINE_RETRIEVAL_TIMEOUT_SECONDS`
- `CUSTOMER_LOST_TIMEOUT_SECONDS`
- `WORKER_RETURN_TIMEOUT_SECONDS`
- `SERVICE_END_CONFIRM_SECONDS`
- `SERVICE_MAX_SECONDS`
- `CUSTOMER_SHORT_GAP_RELINK_SECONDS`
- `CUSTOMER_RELINK_MAX_CENTER_DISTANCE`
- `LOCAL_SESSION_STITCH_*`
- `PHONE_TEMPORAL_WINDOW`
- `PHONE_MIN_POSITIVE_CHECKS`
- `PHONE_CONFIRM_SECONDS`
- `PHONE_HOLD_SECONDS`
- `PHONE_NEAR_HAND_DISTANCE_RATIO`
- `PHONE_NEAR_HEAD_DISTANCE_RATIO`
- `IDLE_CONFIRM_SECONDS`
- `IDLE_EXIT_CONFIRM_SECONDS`
- `IDLE_MIN_TRACK_AGE_SECONDS`
- `IDLE_POSE_GRACE_SECONDS`
- `IDLE_TRACK_GAP_GRACE_SECONDS`
- `IDLE_BODY_MOTION_THRESHOLD`
- `IDLE_WRIST_MOTION_THRESHOLD`
- `IDLE_ELBOW_MOTION_THRESHOLD`
- `IDLE_MIN_EVIDENCE_QUALITY`
- `MOVEMENT_SMOOTHING_WINDOW`
- `POSE_SMOOTHING_WINDOW`
- `IDLE_MIN_EVENT_SECONDS`
- `IDLE_HOLD_SECONDS`

Tune timeouts from reviewed pharmacy footage. Conservative defaults favor an
extra review or split over silently joining different people.

The default customer re-link window is 6 seconds and the conservative worker
stitch candidate window is 12 seconds. Both must remain shorter than the
pharmacy's meaningful departure/return intervals and should be validated at
the actual per-camera processing FPS.

## TEST mode

The camera page has a `TEST` button. It calls the stored per-camera API and
switches the frame request to the TEST rendering. Toggling it does not restart
capture, reset the tracker, close services, or change inference input.

- `GET /cameras/{camera_id}/debug`
- `PUT /cameras/{camera_id}/debug`
- `GET /cameras/{camera_id}/frame.jpg?view=normal`
- `GET /cameras/{camera_id}/frame.jpg?view=test`
- `GET /cameras/{camera_id}/activity-diagnostics`

The detector always reads the clean capture frame. TEST drawings are applied to
a copy after inference. Settings independently control pose, zones, phone boxes,
assignments, and performance statistics.

The manager-only diagnostics endpoint returns the same bounded worker,
customer, and camera evidence shown in TEST mode. It excludes camera source
credentials, encrypted appearance descriptors, and face image data.

## Customer APIs and reports

- `GET /customer-sessions?report_date=YYYY-MM-DD`
- `GET /customer-sessions/{session_id}`
- `POST /customer-sessions/{session_id}/close`
- `PUT /customer-sessions/{session_id}/review`
- `GET /reports/latest/customers/download`

`latest_customer_report.csv` contains the complete journey. The manager HTML
starts with business metrics, then customer journeys, worker summaries,
structured unknown reasons, and finally technical evidence/audit details.

## Privacy and interpretation

Customers are never face-captured or appearance-matched. Worker stitching uses
short-gap camera-local spatial/movement/clothing evidence and retains an audit
record. Global worker appearance association remains optional, day-scoped, and
anonymous. `UNKNOWN` never means inactive; `POSSIBLE_PHONE` always requires
review.
