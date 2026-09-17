# Activity state machine

Status: **Implemented and unit tested** with synthetic evidence.

The engine preserves `current_state`, `candidate_state`, `candidate_started_at`, confidence, reasons and limitations per `track_id`. A candidate must remain stable for the configured confirmation time before it closes the previous event and opens a new one. Priority is `ON_PHONE`, `SERVING_CUSTOMER`, `CASHIER_WORK`, `SHELF_WORK`, `OTHER_WORK`, `POSSIBLE_PHONE`, `POSSIBLE_IDLE`, then `UNKNOWN`.

`ABSENT` is a presence state, not an activity. `UNKNOWN` is never coerced into idle. Phone pose alone never becomes `ON_PHONE`.

