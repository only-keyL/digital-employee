"""文档知识库相关请求/响应模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DocTypeInput = Literal["manual", "requirement", "faq", "other"]


class DocumentUploadMeta(BaseModel):
    """文档上传元数据（multipart 表单字段）。"""

    doc_name: str = Field(..., min_length=1, max_length=200, description="文档名称")
    doc_type: DocTypeInput = Field(default="other", description="文档类型")
    system_name: str | None = Field(default=None, max_length=100, description="所属系统")
    module_name: str | None = Field(default=None, max_length=100, description="所属模块")
    version: str | None = Field(default=None, max_length=50, description="文档版本")


class DocumentDetail(BaseModel):
    """文档主信息详情。"""

    id: int
    doc_name: str
    doc_type: str
    file_name: str
    file_ext: str
    file_size: int
    file_hash: str
    storage_path: str
    system_name: str | None = None
    module_name: str | None = None
    version: str | None = None
    parse_status: str
    parse_error: str | None = None
    chunk_count: int
    enabled: int
    deleted: int
    create_time: datetime
    update_time: datetime


class DocumentChunkDetail(BaseModel):
    """文档切片详情。"""

    id: int
    doc_id: int
    doc_name: str
    chunk_index: int
    section_title: str | None = None
    section_path: str | None = None
    page_no: int | None = None
    content: str
    content_hash: str | None = None
    token_estimate: int
    vector_status: str
    vector_id: str | None = None
    vector_error: str | None = None
    enabled: int
    create_time: datetime
    update_time: datetime


class DocumentVectorSyncResult(BaseModel):
    """向量同步统计结果。"""

    total: int = 0
    synced: int = 0
    failed: int = 0
    deleted: int = 0
