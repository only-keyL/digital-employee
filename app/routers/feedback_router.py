from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.common_schema import error_response, success_response
from app.schemas.feedback_schema import FeedbackCreateRequest
from app.services.feedback_service import FeedbackService, FeedbackServiceError

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("")
def submit_feedback(payload: FeedbackCreateRequest, db: Session = Depends(get_db)):
    try:
        data = FeedbackService(db).submit_feedback(payload)
        return success_response(data, "反馈提交成功")
    except FeedbackServiceError as exc:
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
    db: Session = Depends(get_db),
):
    try:
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
