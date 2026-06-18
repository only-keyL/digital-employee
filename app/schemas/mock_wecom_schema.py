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
    success: bool = Field(default=True, description="业务是否成功；幂等冲突时为 false")
    idempotent: bool = Field(default=False, description="是否命中幂等缓存")
    idempotent_status: str | None = Field(default=None, description="幂等状态：duplicate_success 等")
