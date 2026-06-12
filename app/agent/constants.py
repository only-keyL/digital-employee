"""LangGraph 问答工作流常量（阶段七）。"""

# 固定回答文案
FALLBACK_ANSWER = "当前知识库未找到明确答案，已记录为待沉淀问题，建议人工确认后再处理。"  # 未命中默认回答
RETRIEVAL_ERROR_ANSWER = "当前知识库检索服务暂不可用，已记录为待处理问题，建议人工确认后再处理。"  # 检索异常回答
EMPTY_QUESTION_REASON = "问题不能为空"  # 空问题 fallback_reason
RETRIEVAL_ERROR_REASON = "向量检索异常"  # 检索异常 fallback_reason

# 条件路由返回值（route_after_* 使用）
ROUTE_END = "end"  # 直接结束（如空问题）
ROUTE_CONTINUE = "continue"  # 继续后续节点
ROUTE_ERROR = "error"  # 走 error_fallback 节点
ROUTE_OK = "ok"  # 检索成功，进入 match_judge
ROUTE_MATCHED = "matched"  # 命中，走 generate_answer
ROUTE_MISS = "miss"  # 未命中，走 handle_miss
