"""运营看板 REST API 路由。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.common_schema import error_response, success_response
from app.services.operation_dashboard_service import OperationDashboardService

router = APIRouter(prefix="/api/operation-dashboard", tags=["operation-dashboard"])


@router.get("/summary")
def get_operation_dashboard_summary(
    days: int = Query(7, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """获取运营看板总览指标。"""
    try:
        summary = OperationDashboardService(db).get_summary(days=days)
        return success_response(summary.model_dump())
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.get("/tops")
def get_operation_dashboard_tops(
    days: int = Query(7, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """获取运营看板 Top 列表。"""
    try:
        tops = OperationDashboardService(db).get_top_lists(days=days, limit=limit)
        return success_response(tops.model_dump())
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")
