from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.common_schema import error_response, success_response
from app.services.statistics_service import StatisticsService

router = APIRouter(prefix="/api/statistics", tags=["statistics"])


@router.get("/dashboard")
def get_statistics_dashboard(db: Session = Depends(get_db)):
    try:
        data = StatisticsService(db).get_dashboard()
        return success_response(data)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")
