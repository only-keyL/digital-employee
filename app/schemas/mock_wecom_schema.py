"""模拟企微接口响应模型。"""

from pydantic import BaseModel, Field


class MockWeComResponse(BaseModel):
    message_id: str
    reply_type: str = Field(default="text")
    reply: str
    command: str | None = None
    session_active: bool = False
    run_id: str | None = None
    contribution_id: str | None = None
    knowledge_card_id: int | None = None
    status: str | None = None
