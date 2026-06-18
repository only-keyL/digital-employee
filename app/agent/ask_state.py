"""LangGraph 工作流状态 AskState（阶段七）。"""

from __future__ import annotations

from typing import Any, TypedDict


class AskState(TypedDict, total=False):
    """问答流程在 LangGraph 各节点间传递的共享状态。"""

    # --- 输入 ---
    question_raw: str  # 用户原始问题
    question_masked: str  # 脱敏后问题（当前等于原文）
    rewritten_question: str  # 改写后问题（当前等于原文）
    user_id: str  # 用户 ID
    group_id: str  # 群组 / 会话 ID
    source_type: str  # 来源：web / wecom 等

    # --- 流程控制 ---
    is_valid: bool  # 问题是否有效（非空）
    should_write_log: bool  # 是否写入 question_log
    route: str  # 内部路由标记（continue/end/error 等）
    retrieval_error: bool  # 向量检索是否异常

    # --- 检索（对外响应 + 内部） ---
    matched: bool  # 是否命中知识库
    similarity_score: float  # 最高相似度分数
    confidence_level: str  # 置信度等级：high / medium / low / none
    primary_matched_card_id: int | None  # top1 命中知识卡片 ID
    primary_matched_card_title: str | None  # top1 命中卡片标题
    answer_status: str  # 回答状态：hit / medium_confidence / low_confidence / miss 等
    answer_source: str | None  # 回答来源：qdrant_rag / unanswered / llm_fallback 等
    system_name: str | None  # 问题归属系统
    module_name: str | None  # 问题归属模块
    sources: list[dict[str, Any]]  # 返回前端的来源列表
    matched_card_ids: str  # 命中的卡片 ID，逗号分隔
    retrieval_hits: list[dict[str, Any]]  # 检索 hit 明细（含 card_id/title/score）
    fallback_reason: str | None  # 未命中或降级原因

    # --- 检索原始字段（节点内部） ---
    _raw_matched: bool  # RetrievalService 原始 matched
    _raw_fallback_reason: str | None  # RetrievalService 原始 fallback_reason
    _raw_similarity_score: float  # RetrievalService 原始最高分

    # --- 答案生成 ---
    answer: str  # 最终回答文本
    need_human: bool  # 是否建议人工处理
    risk_level: str  # 风险等级：low / medium 等
    llm_tokens: int | None  # LLM 消耗 token 数
    error_stage: str | None  # 出错阶段（如 llm_generate）
    error_message: str | None  # 出错信息摘要

    # --- 耗时 ---
    started_at: float  # 请求开始时间（perf_counter）
    retrieval_time_ms: int  # 检索耗时（毫秒）
    answer_time_ms: int  # 生成耗时（毫秒）
    latency_ms: int  # 总耗时（毫秒）

    # --- 输出 ---
    question_log_id: int | None  # 写入 question_log 后的主键
    intent: str  # 意图（当前固定 question）
