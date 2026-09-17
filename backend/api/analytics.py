from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.auth import require_manager
from database import get_db
from services.analytics_service import customer_daily_analytics, daily_analytics

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(require_manager)])


@router.get("/daily")
def get_daily(report_date: date | None = None, db: Session = Depends(get_db)):
    return daily_analytics(db, report_date or date.today())


@router.get("/customer-service")
def get_customer_service(report_date: date | None = None, db: Session = Depends(get_db)):
    return customer_daily_analytics(db, report_date or date.today())

