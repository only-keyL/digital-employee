"""用户反馈 REST API 路由（/api/feedback）。"""

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.repositories.feedback_repository import FeedbackRepository
from app.schemas.common_schema import error_response, success_response
from app.schemas.feedback_schema import FeedbackCreateRequest, FeedbackSubmitRequest
from app.services.feedback_evolution_service import FeedbackEvolutionError, FeedbackEvolutionService
from app.services.feedback_service import FeedbackService, FeedbackServiceError

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("")
def submit_feedback(payload: FeedbackSubmitRequest, db: Session = Depends(get_db)):
    """提交问答反馈（有用 / 无用 / 补充）。"""
    try:
        result = FeedbackEvolutionService(db).submit_feedback(payload)
        return success_response(result.to_dict(), result.message)
    except FeedbackEvolutionError as exc:
        return error_response(exc.message)
    except ValidationError as exc:
        return error_response(str(exc.errors()[0]["msg"]))
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.post("/legacy")
def submit_feedback_legacy(payload: FeedbackCreateRequest, db: Session = Depends(get_db)):
    """兼容旧版页面：需显式传入 question_log_id。"""
    try:
        mapped = FeedbackSubmitRequest(
            user_id=payload.user_id or "anonymous",
            feedback_type="useful" if payload.feedback_type == "useful" else "useless",
            question_log_id=payload.question_log_id,
            comment=payload.comment,
            reason_text=payload.comment if payload.feedback_type == "useless" else None,
        )
        if payload.feedback_type == "need_human":
            mapped = FeedbackSubmitRequest(
                user_id=payload.user_id or "anonymous",
                feedback_type="useless",
                question_log_id=payload.question_log_id,
                comment=payload.comment,
                reason_text=payload.comment or "需人工处理",
                reason_type="other",
            )
        result = FeedbackEvolutionService(db).submit_feedback(mapped)
        return success_response(result.to_dict(), result.message)
    except FeedbackEvolutionError as exc:
        return error_response(exc.message)
    except ValidationError as exc:
        return error_response(str(exc.errors()[0]["msg"]))
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.get("")
def list_feedback(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    feedback_type: str | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """分页查询反馈列表，可按类型或状态筛选。"""
    try:
        if status:
            repo = FeedbackRepository(db)
            rows = repo.list_by_status(status=status, offset=(page - 1) * page_size, limit=page_size)
            total = repo.count_by_status(status)
            items = [
                {
                    "id": row.id,
                    "question_log_id": row.question_log_id,
                    "feedback_type": row.feedback_type,
                    "user_id": row.user_id,
                    "knowledge_card_id": row.knowledge_card_id,
                    "status": row.status,
                    "create_time": row.create_time,
                }
                for row in rows
            ]
            return success_response(
                {"items": items, "total": total, "page": page, "page_size": page_size}
            )

        if feedback_type is not None and feedback_type.strip() == "":
            feedback_type = None
        data = FeedbackService(db).list_for_api(
            page=page,
            page_size=page_size,
            feedback_type=feedback_type,
        )
        return success_response(data)
    except FeedbackServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.get("/{feedback_id}")
def get_feedback(feedback_id: int, db: Session = Depends(get_db)):
    """查询单条反馈详情。"""
    try:
        row = FeedbackRepository(db).get_by_id(feedback_id)
        if row is None:
            return error_response("反馈记录不存在")
        return success_response(
            {
                "id": row.id,
                "question_log_id": row.question_log_id,
                "feedback_type": row.feedback_type,
                "user_id": row.user_id,
                "knowledge_card_id": row.knowledge_card_id,
                "group_id": row.group_id,
                "reason_type": row.reason_type,
                "reason_text": row.reason_text,
                "supplement_text": row.supplement_text,
                "status": row.status,
                "create_time": row.create_time,
            }
        )
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")
