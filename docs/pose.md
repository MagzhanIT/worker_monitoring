# Pose

Status: crop-to-frame mapping, freshness, smoothing and validation are **implemented**; pharmacy-specific accuracy is **unmeasured**. COCO-17 keypoints are stored with their inference frame, exact crop, global coordinates, confidence and timestamp. Skipped frames retain fresh points; missing updates decay confidence; stale poses expire. Both endpoints must be valid before a bone is rendered.

