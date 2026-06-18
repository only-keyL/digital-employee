"""模拟企微与真实企微共用的标准消息对象。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class WeComMessage(BaseModel):
    """统一企微消息标准对象。

    当前阶段仅 mock_wecom 来源；阶段 6 真实企微回调将复用本结构，
    在 router 层完成解密后映射为 WeComMessage，业务层无需感知差异。
    """

    message_id: str = Field(description="消息唯一 ID，用于幂等与追踪")
    source: str = Field(default="mock_wecom", description="消息来源：mock_wecom / wecom")
    group_id: str | None = Field(default=None, description="群 ID，私聊为空")
    user_id: str = Field(description="发送用户 ID")
    user_name: str | None = Field(default=None, description="发送用户昵称")
    content: str = Field(description="消息文本内容")
    at_user_ids: list[str] = Field(default_factory=list, description="@ 用户列表")
    create_time: datetime | None = Field(default=None, description="消息时间")
    raw_payload: dict | None = Field(default=None, description="原始 payload，仅调试，禁止完整打日志")
