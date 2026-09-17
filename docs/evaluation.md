# Evaluation

Status: deterministic and offline validation tooling is implemented, but no
pharmacy accuracy claim is made without reviewed ground truth.

Run the live evidence pipeline without the API or UI:

```powershell
cd backend
.venv\Scripts\python.exe offline_video_test.py "C:\footage\camera.mp4" --camera-id 3 --ground-truth "C:\footage\truth.csv" --no-preview
```

It exports an annotated video, event CSV, bounded per-analysis-frame diagnostics
CSV, anonymous customer-journey CSV, JSON summary, and manager HTML report.
Ground truth uses
`camera_id,worker_label,start_seconds,end_seconds,expected_activity,notes`. The
JSON includes a deterministic evidence signature for comparing repeat runs made
with identical footage, zones, configuration, and model versions.

Create consented, camera-specific annotated clips and measure person/role
tracking continuity, phone event precision/recall, activity interval overlap,
customer wait error, unknown coverage, camera availability, processing FPS and
p95 latency. Publish thresholds, confidence intervals and failure slices for
occlusion, crowding, glare, camera angle and small objects.
