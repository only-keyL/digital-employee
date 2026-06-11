"""Pydantic schemas for WeCom callback endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WecomMockCallbackRequest(BaseModel):
    msg_id: str = Field(..., min_length=1)
    from_user: str = "wecom_user_demo"
    to_user: str = "corp_agent"
    chat_id: str = ""
    msg_type: str = "text"
    content: str = ""
    create_time: int | None = None


class WecomInboundMessage(BaseModel):
    msg_id: str
    from_user: str
    to_user: str
    chat_id: str
    msg_type: str
    content: str
    create_time: int | None = None
