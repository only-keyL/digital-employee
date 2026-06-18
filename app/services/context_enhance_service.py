"""上下文增强服务：规则识别追问并改写问题。"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.repositories.question_repository import QuestionRepository
from app.schemas.context_schema import ContextEnhanceResult, ConversationContext
from app.services.conversation_context_service import ConversationContextService

logger = logging.getLogger(__name__)

# 明显追问关键词
FOLLOW_UP_KEYWORDS: tuple[str, ...] = (
    "那",
    "这个",
    "那个",
    "它",
    "刚才",
    "上面",
    "还是",
    "继续",
    "下一步",
    "在哪里",
    "怎么配置",
    "怎么设置",
    "怎么操作",
    "还是不行",
    "仍然不行",
    "还不行",
    "然后呢",
)

# 模糊问题常见表达
VAGUE_EXPRESSION_KEYWORDS: tuple[str, ...] = (
    "怎么办",
    "哪里",
    "怎么",
    "为什么",
    "还是不行",
    "仍然不行",
    "还不行",
)

# 明确系统 / 模块关键词：当前问题已包含时不应被历史上下文覆盖
EXPLICIT_BUSINESS_KEYWORDS: tuple[str, ...] = (
    "合同系统",
    "报销系统",
    "库存系统",
    "审批流",
    "权限配置",
    "回款模块",
    "商机模块",
    "CRM",
    "ERP",
    "OA",
)

STILL_NOT_WORKING_KEYWORDS: tuple[str, ...] = ("还是不行", "仍然不行", "还不行")
CONTEXT_SOURCE_REDIS = "redis_recent_turn"
CONTEXT_SOURCE_MODULES = "user_recent_modules"
CONTEXT_SOURCE_NONE = "none"


class ContextEnhanceService:
    """上下文增强服务。

    负责识别用户是否在追问，并结合 Redis 短期上下文或近 30 天常问系统/模块，
    将模糊问题改写成更适合 RAG 检索的完整问题。
    本服务不调用大模型，不访问 Qdrant，不修改知识卡片。
    """

    def __init__(
        self,
        session: Session,
        *,
        conversation_service: ConversationContextService | None = None,
        question_repo: QuestionRepository | None = None,
    ) -> None:
        self.session = session
        self.conversation_service = conversation_service or ConversationContextService()
        self.question_repo = question_repo or QuestionRepository(session)

    async def enhance_question_async(
        self,
        *,
        question: str,
        user_id: str,
        group_id: str | None,
    ) -> ContextEnhanceResult:
        """异步上下文增强，供企微模拟等 async 链路调用。"""
        original = (question or "").strip()
        if not original:
            return self._no_enhance_result("")

        # 当前问题已经包含明确系统/模块时，优先尊重用户当前表达
        if self.has_explicit_business_context(original):
            return self._no_enhance_result(original)

        recent_context = await self.conversation_service.get_recent_context(
            user_id=user_id,
            group_id=group_id,
        )
        is_follow_up = self.is_follow_up_question(original)

        if is_follow_up and recent_context is not None:
            rewritten = self.rewrite_with_recent_context(original, recent_context)
            return ContextEnhanceResult(
                original_question=original,
                rewritten_question=rewritten,
                used_context=True,
                context_source=CONTEXT_SOURCE_REDIS,
                context_summary=self._build_redis_summary(recent_context),
            )

        if self._should_use_recent_modules(original, is_follow_up=is_follow_up):
            modules = self.question_repo.list_user_recent_modules(
                user_id=user_id,
                group_id=group_id,
                days=30,
                limit=3,
            )
            if modules:
                rewritten = self.rewrite_with_recent_modules(original, modules)
                top = modules[0]
                return ContextEnhanceResult(
                    original_question=original,
                    rewritten_question=rewritten,
                    used_context=True,
                    context_source=CONTEXT_SOURCE_MODULES,
                    context_summary=f"{top.get('system_name')}/{top.get('module_name')}",
                )

        return self._no_enhance_result(original)

    def enhance_question(
        self,
        *,
        question: str,
        user_id: str,
        group_id: str | None,
    ) -> ContextEnhanceResult:
        """同步上下文增强，供 /api/ask 链路调用。"""
        import asyncio

        return asyncio.run(
            self.enhance_question_async(
                question=question,
                user_id=user_id,
                group_id=group_id,
            )
        )

    def is_follow_up_question(self, question: str) -> bool:
        """判断当前问题是否属于依赖上一轮语义的追问。"""
        text = (question or "").strip()
        if not text:
            return False

        if any(keyword in text for keyword in FOLLOW_UP_KEYWORDS):
            return True

        # 简短模糊问题也倾向视为追问
        if len(text) <= 20 and not self.has_explicit_business_context(text):
            if any(keyword in text for keyword in VAGUE_EXPRESSION_KEYWORDS):
                return True

        return False

    def has_explicit_business_context(self, question: str) -> bool:
        """判断当前问题是否已经包含明确系统/模块信息。"""
        text = (question or "").strip()
        if not text:
            return False
        return any(keyword in text for keyword in EXPLICIT_BUSINESS_KEYWORDS)

    def rewrite_with_recent_context(self, question: str, context: ConversationContext) -> str:
        """基于 Redis 最近一轮问答上下文改写追问。"""
        system_name = (context.system_name or "未知系统").strip()
        module_name = (context.module_name or "未知模块").strip()
        last_question = (context.last_question or "").strip()

        if any(keyword in question for keyword in STILL_NOT_WORKING_KEYWORDS):
            return (
                f"在{system_name}的{module_name}场景下，用户已按上一轮答案处理但仍未解决，"
                f"继续排查：{last_question or question}"
            )

        return (
            f"在{system_name}的{module_name}场景下，针对「{last_question}」这个问题，"
            f"继续追问：{question}"
        )

    def rewrite_with_recent_modules(self, question: str, modules: list[dict]) -> str:
        """基于用户近 30 天常问系统/模块轻量增强问题。"""
        if not modules:
            return question
        top = modules[0]
        system_name = (top.get("system_name") or "未知系统").strip()
        module_name = (top.get("module_name") or "未知模块").strip()
        return f"结合用户近 30 天常问的{system_name} / {module_name}，查询：{question}"

    def _should_use_recent_modules(self, question: str, *, is_follow_up: bool) -> bool:
        """判断是否可以尝试 30 天常问系统/模块增强。"""
        text = (question or "").strip()
        if not text:
            return False
        if self.has_explicit_business_context(text):
            return False

        if is_follow_up:
            return True

        if len(text) <= 20:
            return True

        return any(keyword in text for keyword in VAGUE_EXPRESSION_KEYWORDS)

    @staticmethod
    def _no_enhance_result(original: str) -> ContextEnhanceResult:
        """未使用上下文增强时的默认结果。"""
        return ContextEnhanceResult(
            original_question=original,
            rewritten_question=original,
            used_context=False,
            context_source=CONTEXT_SOURCE_NONE,
            context_summary=None,
        )

    @staticmethod
    def _build_redis_summary(context: ConversationContext) -> str:
        """构建 Redis 上下文摘要，便于日志排查。"""
        parts = [context.last_question or ""]
        if context.system_name or context.module_name:
            parts.append(f"{context.system_name}/{context.module_name}")
        return " | ".join(part for part in parts if part)
