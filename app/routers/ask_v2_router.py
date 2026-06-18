"""AskGraphV2 问答 API（不替换原 /api/ask）。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.graphs.ask_graph_v2 import AskGraphV2Runner
from app.schemas.ask_v2_schema import AskV2Request, AskV2Response, AskV2RetrievalItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ask-v2"])


async def _handle_ask_v2(payload: AskV2Request, db: Session) -> AskV2Response:
    runner = AskGraphV2Runner(db)
    state = await runner.run(
        question=payload.question,
        user_id=payload.user_id,
        source=payload.source,
    )
    retrieval = []
    for ctx in state.get("contexts") or []:
        retrieval.append(
            AskV2RetrievalItem(
                knowledge_id=ctx.knowledge_id,
                title=ctx.title,
                score=ctx.score,
                rank=ctx.rank,
            )
        )
    return AskV2Response(
        run_id=state["run_id"],
        status=state.get("status") or "failed",
        confidence_level=state.get("confidence_level") or "none",
        top_score=state.get("top_score"),
        answer=state.get("answer") or "",
        retrieval=retrieval,
        fallback_reason=state.get("fallback_reason"),
    )


@router.post("/ask-v2", response_model=AskV2Response)
async def ask_v2(payload: AskV2Request, db: Session = Depends(get_db)) -> AskV2Response:
    """Stage3 RAG 问答接口。"""
    return await _handle_ask_v2(payload, db)


@router.post("/mock/ask-v2", response_model=AskV2Response)
async def mock_ask_v2(payload: AskV2Request, db: Session = Depends(get_db)) -> AskV2Response:
    """Mock 入口：默认 source=mock_ask_v2。"""
    payload.source = payload.source or "mock_ask_v2"
    return await _handle_ask_v2(payload, db)
