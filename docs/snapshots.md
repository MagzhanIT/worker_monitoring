# Worker snapshots

Status: quality scoring, safe paths and worker-only selection are **implemented**; face detection depends on an optional local detector.

Up to three face crops and two body crops are retained by quality for likely-worker sessions. Small, dark, blurred, ambiguous, customer or uncertain-role candidates are rejected. Identity is not automatically recognized. Images are provided only for authorized manager visual reference.

