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
from app.services.message_idempotency_service import MessageIdempotencyService
from app.wecom.command_router import CommandRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mock/wecom", tags=["mock-wecom"])


class MockWeComMessageRequest(WeComMessage):
    """模拟企微消息请求，message_id 可省略自动生成。"""


def _response_from_cache(data: dict) -> MockWeComResponse:
    """从幂等缓存重建响应，并标记 idempotent=true。"""
    payload = dict(data)
    payload["idempotent"] = True
    payload["idempotent_status"] = payload.pop("idempotent_status", "duplicate_success")
    return MockWeComResponse(**payload)


@router.post("/message", response_model=MockWeComResponse)
async def mock_wecom_message(
    payload: MockWeComMessageRequest,
    db: Session = Depends(get_db),
) -> MockWeComResponse:
    """模拟企微群/私聊消息：指令、问答、知识投稿统一入口（含 message_id 幂等）。"""
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
    source = message.source or "mock_wecom"
    idem = MessageIdempotencyService(db)
    begin = idem.begin_process(
        source=source,
        message_id=message.message_id,
        content=message.content or "",
        group_id=message.group_id,
        user_id=message.user_id,
    )
    status = begin.get("status")

    if status == "duplicate_success":
        cached = begin.get("response") or {}
        cached["idempotent_status"] = "duplicate_success"
        resp = _response_from_cache(cached)
        db.commit()
        return resp

    if status == "duplicate_conflict":
        db.commit()
        return MockWeComResponse(
            message_id=message.message_id,
            reply=str(begin.get("message") or "该消息编号已被处理，但本次内容与首次内容不一致，已拒绝重复处理。"),
            command="duplicate_conflict",
            success=False,
            status="duplicate_conflict",
            idempotent=True,
            idempotent_status="duplicate_conflict",
        )

    if status == "duplicate_processing":
        db.commit()
        return MockWeComResponse(
            message_id=message.message_id,
            reply=str(begin.get("message") or "该消息正在处理中，请勿重复提交。"),
            command="duplicate_processing",
            success=False,
            status="duplicate_processing",
            idempotent=True,
            idempotent_status="duplicate_processing",
        )

    router_service = CommandRouter(db)
    try:
        response = await router_service.route(message)
        response_dict = response.model_dump()
        response_dict["idempotent"] = False
        response_dict["idempotent_status"] = status if status in {"new", "retry_failed"} else None
        idem.mark_success(
            source=source,
            message_id=message.message_id,
            command=response.command,
            response=response_dict,
        )
        db.commit()
        return MockWeComResponse(**response_dict)
    except Exception as exc:
        logger.exception("mock_wecom 处理失败 message_id=%s", message.message_id)
        idem.mark_failed(source=source, message_id=message.message_id, error_message=str(exc))
        db.commit()
        raise
