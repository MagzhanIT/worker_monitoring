from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from api.auth import require_manager
from database import get_db
from schemas.report import ReportRequest, ReportResult
from services.report_service import REPORT_DIR, generate_reports

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(require_manager)])


@router.post("/generate", response_model=ReportResult)
def generate(payload: ReportRequest, db: Session = Depends(get_db)):
    report_date = date.fromisoformat(payload.report_date) if payload.report_date else date.today()
    return generate_reports(db, report_date)


def _file(name: str, media_type: str) -> FileResponse:
    path = REPORT_DIR / name
    if not path.is_file():
        raise HTTPException(404, "Generate a report first")
    return FileResponse(path, media_type=media_type, filename=name)


@router.get("/latest")
def latest():
    path = REPORT_DIR / "latest_report.csv"
    return {"available": path.is_file(), "updated_at": path.stat().st_mtime if path.is_file() else None}


@router.get("/latest/download")
def latest_download():
    return _file("latest_report.csv", "text/csv")


@router.get("/latest/events/download")
def events_download():
    return _file("latest_events.csv", "text/csv")


@router.get("/latest/customers/download")
def customers_download():
    return _file("latest_customer_report.csv", "text/csv")


@router.get("/latest/manager-html")
def manager_html():
    return _file("latest_manager_report.html", "text/html")
