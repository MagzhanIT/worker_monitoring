# Pharmacy Worker Monitor V2

**Pharmacy Operations Analytics using existing CCTV.**

This pre-production implementation turns pharmacy camera feeds into conservative, reviewable operational events. It uses FastAPI, SQLite, SQLAlchemy, OpenCV/Ultralytics integration points, WebSockets, local CSV/HTML reports, and a responsive Flutter manager application. Real-site accuracy, fairness, latency, and failure behavior still require measured validation before production deployment.

## Safety and privacy boundary

- Worker sessions and customers are anonymous.
- Face detection may crop a good manager-reference image for a likely worker only; there is no face recognition or face embedding.
- Worker sessions can receive a day-scoped global anonymous ID across cameras using encrypted clothing/body appearance. This is not legal identity, can be wrong with similar uniforms, and exposes match status/confidence for manager review. Customers are never appearance-matched.
- Customer journeys persist waiting, direct service, medicine retrieval, return, transaction, completion, abandonment, and interruption phases. Medicine retrieval remains inside total service time.
- Per-camera TEST mode renders pose, zones, phone candidates, assignments, IDs, phases, timers, unknown reasons, and performance diagnostics on a copy of the clean source frame.
- Customer face snapshots are never deliberately stored.
- The system reports observed, possible, unknown, and unavailable periods separately. It does not decide pay, discipline, laziness, or employee quality.
- `ON_PHONE` requires temporally confirmed physical-phone evidence. Pose or a `phone_call` class alone can produce only `POSSIBLE_PHONE`.
- Camera failure produces `UNKNOWN`/`CAMERA_UNAVAILABLE`, never idle or absence.

## Quick start

macOS: copy `.env.example` to `.env`, provide a strong secret and optional admin password, then double-click `SETUP_MAC.command` and `START_BACKEND_MAC.command`.

Windows: copy `.env.example` to `.env`, then double-click `SETUP_WINDOWS_DOUBLE_CLICK.bat` and `START_BACKEND_WINDOWS.bat`.

The API is served at `http://localhost:8000`, with interactive documentation at `/docs`. Model weights are not bundled; see `backend/models/README.md`. Without models, health and reporting remain available and perception is marked unavailable.

See `docs/architecture.md`, `docs/mac_setup.md`, `docs/windows_setup.md`, and `docs/limitations.md`.

## Maturity

| Area | Status |
|---|---|
| API, database, auth, zones, reports, reviews | Implemented reference system |
| Capture, tracking, health, temporal state logic | Implemented and unit tested |
| YOLO/pose/phone integration | Implemented adapter; accuracy unmeasured without site models/data |
| Flutter manager interface | Implemented student prototype |
| Real-pharmacy accuracy and reliability | Not measured; pilot work required |

## Headless backend video test

You can test the real person, pose, phone, zone, tracking, and evidence pipeline
against a local video without starting the API or mobile app.

On Windows, double-click `TEST_BACKEND_VIDEO_WINDOWS.bat` and paste the video
path. The test writes an annotated MP4, event CSV, diagnostics CSV, customer
journey CSV, repeatable JSON summary, and manager HTML report next to the input
by default. Supplying a camera ID reads that camera's saved zones without
changing the database; `--zones-json` can instead supply a reviewed normalized
zone configuration. The batch file displays the annotated video while it is
processed; press `Q` or `Esc` in that window to stop safely. Command-line users
can add `--no-preview` to disable the window.

Command-line example:

```powershell
cd backend
.venv\Scripts\python.exe offline_video_test.py "C:\path\video.mp4" --camera-id 6
```

Optional ground-truth scoring uses anonymous labels and exports a confusion
matrix, per-class precision/recall/F1, idle timing errors, false/missed idle
counts, UNKNOWN percentage, and reliable-classification coverage:

```powershell
.venv\Scripts\python.exe offline_video_test.py "C:\path\video.mp4" --camera-id 6 --ground-truth "C:\path\truth.csv"
```

The CSV columns are `camera_id`, `worker_label`, `start_seconds`,
`end_seconds`, `expected_activity`, and optional `notes`. Supported activities
are `WORKING`, `SERVING_CUSTOMER`, `FETCHING_MEDICINE`, `SHELF_WORK`,
`POS_WORK`, `IDLE`, `PHONE`, and `UNKNOWN`.

For a faster preview, add `--analysis-every 5`. Every video frame is still
written, but AI analysis runs on every fifth frame. Add `--max-seconds 10` for a
short smoke test. The output video does not copy the input audio.

The Windows test also offers the imported Codea model profile and a reviewed
tracking-dataset export. The equivalent command is:

```powershell
TEST_BACKEND_VIDEO_WINDOWS.bat "C:\path\video.mp4" --codea-models --dataset-dir "C:\worker_review"
```

The export contains only confirmed worker body crops plus `worker_crops.csv`;
customer crops are never saved. These are pseudo-labels for human review, not
training ground truth. Worker labels in the offline video are anonymous and
video-local. Short detector losses are recovered with motion prediction and a
conservative clothing/spatial stitch, but identical uniforms can still cause
ambiguity.

Detector cleanup is deliberately conservative: person and coat boxes belonging
to the same person are fused, isolated verifier-only coat boxes are discarded,
tiny malformed boxes are rejected, and a new track must appear in two
consecutive analyzed frames before it is displayed. Confirmed tracks retain the
existing short-loss grace period, so this filtering does not reset an active
worker session.

## Multi-camera anonymous worker IDs

Each detector track remains camera-local. After several clear worker crops, the
backend can attach the session to a global ID such as `GW-20260725-ABC123`.
Matching is worker-only and limited to the same calendar day. It uses encrypted
clothing/body descriptors, a strict similarity threshold, a second-best margin,
and an active-camera conflict gate. If two identities look too similar, they are
kept separate for review instead of silently merged.

Manager endpoints:

- `GET /worker-identities` lists global IDs, cameras, session counts, and review status.
- `GET /worker-identities/{id}/sessions` shows the camera-local evidence behind an ID.
- `POST /worker-identities/{id}/assign-session/{session_id}` confirms or corrects a session assignment.

Reports group linked sessions under the global anonymous ID and remove
overlapping camera intervals from observed-time totals. Reports always retain
camera IDs, session IDs, match method/status, confidence, and the full event
timeline. Appearance descriptors expire separately from report/session history.

## Customer service and TEST mode

Customer sessions are camera-local and one-to-one by default. A worker who moves
from the counter to a configured `medicine_shelf`, `storage`,
`shelf_interaction`, `computer`, or `pos` zone remains assigned to the same
customer until a configured timeout or confirmed outcome. See
`docs/customer_service_and_test_mode.md` for required zones, settings, APIs, and
manager-report fields.
