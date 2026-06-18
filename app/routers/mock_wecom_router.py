"""模拟企微消息入口 API（不接真实企微回调）。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.mock_wecom_schema import MockWeComResponse
from app.schemas.wecom_message_schema import WeComMessage
from app.wecom.command_router import CommandRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mock/wecom", tags=["mock-wecom"])


class MockWeComMessageRequest(WeComMessage):
    """模拟企微消息请求，message_id 可省略自动生成。"""


@router.post("/message", response_model=MockWeComResponse)
async def mock_wecom_message(
    payload: MockWeComMessageRequest,
    db: Session = Depends(get_db),
) -> MockWeComResponse:
    """模拟企微群/私聊消息：指令、问答、知识投稿统一入口。"""
    message = WeComMessage(
        message_id=payload.message_id or str(uuid.uuid4()),
        source=payload.source or "mock_wecom",
        group_id=payload.group_id,
        user_id=payload.user_id,
        user_name=payload.user_name,
        content=payload.content,
        at_user_ids=payload.at_user_ids,
        create_time=payload.create_time or datetime.now(),
        raw_payload=payload.raw_payload,
    )
    router_service = CommandRouter(db)
    return await router_service.route(message)
