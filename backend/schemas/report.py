from pydantic import BaseModel


class ReportRequest(BaseModel):
    report_date: str | None = None


class ReportResult(BaseModel):
    success: bool
    local_reports_created: bool
    google_sheets_uploaded: bool
    google_sheets_error: str | None
    files: dict[str, str]

