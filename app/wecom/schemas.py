"""Pydantic schemas for WeCom callback endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WecomMockCallbackRequest(BaseModel):
    """本地 Mock 企业微信回调请求体。"""

    msg_id: str = Field(..., min_length=1)  # 消息唯一 ID
    from_user: str = "wecom_user_demo"
    to_user: str = "corp_agent"
    chat_id: str = ""
    msg_type: str = "text"
    content: str = ""
    create_time: int | None = None


class WecomInboundMessage(BaseModel):
    """统一的企业微信入站消息（Mock/XML 解析后）。"""

    msg_id: str  # 消息唯一 ID
    from_user: str  # 发送方用户
    to_user: str  # 接收方（企业应用）
    chat_id: str  # 群聊/会话 ID
    msg_type: str  # 消息类型（如 text）
    content: str  # 文本内容
    create_time: int | None = None  # 消息时间戳
