"""Constants for LangGraph ask workflow (Phase 7)."""

FALLBACK_ANSWER = "当前知识库未找到明确答案，已记录为待沉淀问题，建议人工确认后再处理。"
RETRIEVAL_ERROR_ANSWER = "当前知识库检索服务暂不可用，已记录为待处理问题，建议人工确认后再处理。"
EMPTY_QUESTION_REASON = "问题不能为空"
RETRIEVAL_ERROR_REASON = "向量检索异常"

ROUTE_END = "end"
ROUTE_CONTINUE = "continue"
ROUTE_ERROR = "error"
ROUTE_OK = "ok"
ROUTE_MATCHED = "matched"
ROUTE_MISS = "miss"
