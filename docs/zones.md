# Camera zones

Status: normalized polygon validation, membership and API are **implemented**; calibration for a real camera is **planned**.

Zones are tied to camera configuration version and use `[x, y]` coordinates in `[0, 1]`. Supported formal types are employee, customer, cashier, register interaction, shelf interaction, service position, waiting, entrance, authorized out-of-zone, break and ignore. Purpose is never inferred from display text.

Standing membership uses bottom-centre; interaction membership uses fresh wrists. The Flutter editor reverses `BoxFit.contain` letterboxing before normalization.

