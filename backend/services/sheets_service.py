from __future__ import annotations

from config import settings


def upload_aggregates(rows: list[dict]) -> tuple[bool, str | None]:
    if not settings.google_sheets_enabled:
        return False, None
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        credentials = Credentials.from_service_account_file(
            settings.google_sheets_credentials_file,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        client = gspread.authorize(credentials)
        sheet = client.open_by_key(settings.google_sheets_spreadsheet_id).sheet1
        if rows:
            headers = list(rows[0])
            sheet.append_rows([headers] + [[row.get(key) for key in headers] for row in rows], value_input_option="USER_ENTERED")
        return True, None
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"[:300]

