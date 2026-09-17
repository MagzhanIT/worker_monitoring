# Phone detection

Status: model inspection, periodic/focused crop scheduling, association diagnostics and temporal confirmation are **implemented** as a reference pipeline.

Physical classes (`phone`, `cell phone`, `mobile phone`, `smartphone`) and behavior class (`phone_call`) are separated. Pose or `phone_call` alone produces at most `POSSIBLE_PHONE`. `ON_PHONE` requires an associated physical phone in at least two of five valid checks and releases after configured misses. Real-site precision/recall is not measured.

