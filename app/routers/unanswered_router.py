"""未命中问题 REST API 路由（/api/unanswered-questions）。"""

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.common_schema import error_response, success_response
from app.schemas.unanswered_schema import UnansweredConvertRequest
from app.services.unanswered_convert_service import UnansweredConvertError
from app.services.unanswered_service import UnansweredService

router = APIRouter(prefix="/api/unanswered-questions", tags=["unanswered-questions"])


@router.get("")
def list_unanswered_questions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """分页查询未命中问题列表。"""
    try:
        if status is not None and status.strip() == "":
            status = None
        data = UnansweredService(db).list_for_api(page=page, page_size=page_size, status=status)
        return success_response(data)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.get("/{unanswered_id}")
def get_unanswered_question(unanswered_id: int, db: Session = Depends(get_db)):
    """获取单条未命中问题详情。"""
    try:
        data = UnansweredService(db).get_detail(unanswered_id)
        return success_response(data)
    except UnansweredConvertError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.post("/{unanswered_id}/generate-draft")
def generate_unanswered_draft(unanswered_id: int, db: Session = Depends(get_db)):
    """为 pending 未命中问题生成知识卡片草稿预览。"""
    try:
        data = UnansweredService(db).generate_draft_preview(unanswered_id)
        return success_response(data, "草稿预览生成成功")
    except UnansweredConvertError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.post("/{unanswered_id}/convert")
def convert_unanswered_to_draft(
    unanswered_id: int,
    payload: UnansweredConvertRequest,
    db: Session = Depends(get_db),
):
    """将未命中问题转为 draft 知识卡片。"""
    try:
        data = UnansweredService(db).convert_to_draft(unanswered_id, payload)
        return success_response(data, "已转为知识卡片 draft")
    except UnansweredConvertError as exc:
        return error_response(exc.message)
    except ValidationError as exc:
        return error_response(str(exc.errors()[0]["msg"]))
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.post("/{unanswered_id}/ignore")
def ignore_unanswered_question(unanswered_id: int, db: Session = Depends(get_db)):
    """忽略未命中问题（不再跟进）。"""
    try:
        data = UnansweredService(db).ignore(unanswered_id)
        return success_response(data, "已忽略")
    except UnansweredConvertError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")
