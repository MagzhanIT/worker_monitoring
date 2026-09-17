# Testing

Status: synthetic unit/API tests are **implemented**; live camera, model and device testing are **planned**.

Run `python -m compileall -q .` and `pytest -q` from `backend`. Run `flutter pub get` and `dart analyze` from `mobile_app`. Tests use temporary SQLite databases and synthetic geometry/evidence; they do not claim field accuracy.

