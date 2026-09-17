# E-drive worker-tracking smoke audit

Run date: 2026-07-25

## Scope

- 16 pharmacy clips from `E:\`, `E:\person*.mp4`, and `E:\test_cases\test*.mp4`.
- First 2 seconds of each clip; 50 written frames and 10 analyzed frames per clip.
- Person/employee and lab-coat verifier models enabled.
- Pose and phone inference disabled to isolate detection and tracking behavior.
- No camera ID was supplied, so no activity zones were loaded and work status was not evaluated.

## Aggregate result

- All 16 runs completed and all 16 annotated MP4 files are readable.
- 800 frames written and 160 frames analyzed.
- 500 primary-model candidates and 54 verifier coat candidates were processed.
- Fusion removed 236 duplicate/isolated person-coat boxes before tracking.
- 318 clean tracking detections remained.
- 36 stable local track IDs and 21 anonymous worker sessions were observed.
- Geometry filtering rejected 0 boxes in these segments; the temporal two-hit gate remains responsible for suppressing brief one-frame tracks.

## Per-clip result

| Clip | Stable track IDs | Worker sessions | Maximum visible |
|---|---:|---:|---:|
| root_test4 | 3 | 3 | 3 |
| person | 1 | 0 | 1 |
| person_halat | 5 | 3 | 5 |
| person_halat1 | 2 | 1 | 2 |
| person_halat2 | 2 | 0 | 2 |
| person_halat3 | 3 | 0 | 2 |
| person_halat4 | 0 | 0 | 0 |
| person_halat5 | 1 | 1 | 1 |
| case_test | 1 | 1 | 1 |
| case_test1 | 5 | 3 | 5 |
| case_test2 | 1 | 1 | 1 |
| case_test3 | 3 | 3 | 3 |
| case_test4 | 3 | 3 | 3 |
| case_test5 | 2 | 0 | 2 |
| case_test6 | 3 | 1 | 3 |
| case_test7 | 1 | 1 | 1 |

## Interpretation and risks

- `test_4` retained three clear worker identities with no duplicate coat tracks.
- `person` remained a person with unknown role rather than being forced to worker.
- Blue or non-white staff clothing can remain unknown because the supplied worker model is lab-coat oriented.
- White or patterned clothing can resemble the training class. Camera zones and manager review remain necessary; the coat model alone is not a real employee identity system.
- `person_halat4` had no confirmed detection during only its first two seconds; this is not a conclusion about the remainder of that 81-second video.
- Without saved camera zones and pose evidence, `INSUFFICIENT_EVIDENCE` is the correct activity result. It must not be converted to idle/not-working.

Every row has a corresponding annotated MP4 and JSON evidence summary in this directory.
