from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.ask_schema import AskRequest, AskResponse
from app.services.ask_service import AskService

router = APIRouter(prefix="/api", tags=["ask"])

_RETRIEVAL_ERROR_ANSWER = "当前知识库检索服务暂不可用，已记录为待处理问题，建议人工确认后再处理。"


@router.post("/ask", response_model=AskResponse)
def ask_question(payload: AskRequest, db: Session = Depends(get_db)) -> AskResponse:
    try:
        return AskService(db).ask(payload)
    except SQLAlchemyError:
        return AskResponse(
            matched=False,
            answer="",
            sources=[],
            similarity_score=0.0,
            question_log_id=None,
            fallback_reason="数据库操作失败",
            need_human=False,
            risk_level="low",
        )
    except Exception:
        return AskResponse(
            matched=False,
            answer=_RETRIEVAL_ERROR_ANSWER,
            sources=[],
            similarity_score=0.0,
            question_log_id=None,
            fallback_reason="向量检索异常",
            need_human=True,
            risk_level="medium",
        )
