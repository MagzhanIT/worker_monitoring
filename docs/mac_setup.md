# macOS setup

Status: setup script is **implemented** for Python 3.11/3.12 and an installed Flutter SDK.

1. Copy `.env.example` to `.env` and set a unique `APP_SECRET_KEY`. Set `DEFAULT_ADMIN_PASSWORD` only if the installer should create an admin.
2. Put licensed model files in `backend/models`.
3. Double-click `SETUP_MAC.command`.
4. Double-click `START_BACKEND_MAC.command`.
5. From `mobile_app`, run `flutter run -d chrome` for the manager UI.

