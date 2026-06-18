"""企微模拟消息 CommandRouter：分发指令、问答与知识沉淀。"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.core.desensitize import sanitize_text
from app.graphs.ask_graph_v2 import AskGraphV2Runner
from app.graphs.knowledge_deposit_graph import KnowledgeDepositGraphRunner
from app.infra.redis_client import RedisClientError
from app.schemas.mock_wecom_schema import MockWeComResponse
from app.schemas.wecom_message_schema import WeComMessage
from app.services.context_enhance_service import ContextEnhanceService
from app.services.conversation_context_service import ConversationContextService
from app.services.deposit_session_service import DepositSessionService
from app.services.feedback_evolution_service import FeedbackEvolutionError, FeedbackEvolutionService
from app.wecom.command_detector import CommandDetector, CommandType
from app.wecom.knowledge_template import (
    DEPOSIT_CANCEL_REPLY,
    DEPOSIT_START_HINT,
    DEPOSIT_TEMPLATE_WITHOUT_SESSION_HINT,
    get_template_text,
)

logger = logging.getLogger(__name__)


class CommandRouter:
    """模拟企微消息路由：指令 / 问答 / 知识投稿。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.detector = CommandDetector()
        self.deposit_session = DepositSessionService()
        self.ask_runner = AskGraphV2Runner(session)
        self.deposit_runner = KnowledgeDepositGraphRunner(session)

    async def route(self, message: WeComMessage) -> MockWeComResponse:
        """根据消息类型分发到对应处理器。"""
        if not message.message_id:
            message.message_id = str(uuid.uuid4())

        session_active = False
        try:
            session_active = await self.deposit_session.is_active(message)
        except RedisClientError as exc:
            logger.error("Redis 不可用，无法查询沉淀 session：%s", exc)
            return MockWeComResponse(
                message_id=message.message_id,
                reply=f"Redis 服务暂时不可用，无法进入沉淀模式：{exc}",
                command="error",
                session_active=False,
            )

        command = self.detector.detect(message.content, deposit_session_active=session_active)
        logger.info(
            "CommandRouter message_id=%s command=%s session=%s content=%s",
            message.message_id,
            command.value,
            session_active,
            self.deposit_session.safe_log_content(message.content),
        )

        if command == CommandType.DEPOSIT_START:
            return await self._handle_deposit_start(message)
        if command == CommandType.TEMPLATE:
            return await self._handle_template(message, session_active)
        if command == CommandType.DEPOSIT_CANCEL:
            return await self._handle_deposit_cancel(message)
        if command == CommandType.KNOWLEDGE_SUBMIT:
            return await self._handle_knowledge_submit(message)

        # 反馈指令优先于普通 RAG 问答，避免「有用」「无用」进入检索链路
        if FeedbackEvolutionService.is_feedback_text(message.content or ""):
            return await self._handle_feedback(message)

        return await self._handle_normal_question(message)

    async def _handle_deposit_start(self, message: WeComMessage) -> MockWeComResponse:
        try:
            await self.deposit_session.create_session(message)
        except RedisClientError as exc:
            return MockWeComResponse(
                message_id=message.message_id,
                reply=f"无法进入沉淀模式：{exc}",
                command=CommandType.DEPOSIT_START.value,
                session_active=False,
            )
        return MockWeComResponse(
            message_id=message.message_id,
            reply=DEPOSIT_START_HINT,
            command=CommandType.DEPOSIT_START.value,
            session_active=True,
        )

    async def _handle_template(self, message: WeComMessage, session_active: bool) -> MockWeComResponse:
        prefix = "" if session_active else DEPOSIT_TEMPLATE_WITHOUT_SESSION_HINT
        return MockWeComResponse(
            message_id=message.message_id,
            reply=prefix + get_template_text(),
            command=CommandType.TEMPLATE.value,
            session_active=session_active,
        )

    async def _handle_deposit_cancel(self, message: WeComMessage) -> MockWeComResponse:
        try:
            await self.deposit_session.delete_session(message)
        except RedisClientError as exc:
            return MockWeComResponse(
                message_id=message.message_id,
                reply=f"取消沉淀失败：{exc}",
                command=CommandType.DEPOSIT_CANCEL.value,
                session_active=False,
            )
        return MockWeComResponse(
            message_id=message.message_id,
            reply=DEPOSIT_CANCEL_REPLY,
            command=CommandType.DEPOSIT_CANCEL.value,
            session_active=False,
        )

    async def _handle_knowledge_submit(self, message: WeComMessage) -> MockWeComResponse:
        try:
            await self.deposit_session.refresh_session(message)
        except RedisClientError:
            pass

        state = await self.deposit_runner.run(message)
        exit_session = bool(state.get("exit_session"))
        if exit_session:
            try:
                await self.deposit_session.delete_session(message)
            except RedisClientError:
                logger.warning("投稿完成后删除 session 失败 user=%s", message.user_id)

        return MockWeComResponse(
            message_id=message.message_id,
            reply=state.get("reply") or "投稿处理完成",
            command=CommandType.KNOWLEDGE_SUBMIT.value,
            session_active=not exit_session,
            contribution_id=state.get("contribution_id"),
            knowledge_card_id=state.get("knowledge_card_id"),
            status=state.get("status"),
        )

    async def _handle_feedback(self, message: WeComMessage) -> MockWeComResponse:
        """处理文本反馈：有用 / 无用 / 补充。"""
        svc = FeedbackEvolutionService(self.session)
        try:
            result = svc.submit_text_feedback(
                text=message.content or "",
                user_id=message.user_id or "anonymous",
                group_id=message.group_id,
            )
            return MockWeComResponse(
                message_id=message.message_id,
                reply=result.message,
                command="feedback",
                session_active=False,
                status=result.feedback_type,
            )
        except FeedbackEvolutionError as exc:
            return MockWeComResponse(
                message_id=message.message_id,
                reply=exc.message,
                command="feedback",
                session_active=False,
                status="feedback_failed",
            )

    async def _handle_normal_question(self, message: WeComMessage) -> MockWeComResponse:
        enhance_svc = ContextEnhanceService(self.session)
        enhance_result = await enhance_svc.enhance_question_async(
            question=message.content or "",
            user_id=message.user_id or "anonymous",
            group_id=message.group_id,
        )
        state = await self.ask_runner.run(
            question=enhance_result.rewritten_question,
            original_question=enhance_result.original_question,
            rewritten_question=enhance_result.rewritten_question,
            used_context=1 if enhance_result.used_context else 0,
            context_source=enhance_result.context_source,
            context_summary=enhance_result.context_summary,
            user_id=message.user_id,
            group_id=message.group_id,
            source="mock_wecom",
        )
        answer = (state.get("answer") or "").strip()
        if answer and (message.user_id or "").strip():
            try:
                await ConversationContextService().save_recent_context(
                    user_id=message.user_id,
                    group_id=message.group_id,
                    question=enhance_result.original_question,
                    rewritten_question=enhance_result.rewritten_question,
                    answer=answer,
                    system_name=state.get("system_name"),
                    module_name=state.get("module_name"),
                    primary_matched_card_id=state.get("primary_matched_card_id"),
                    primary_matched_card_title=state.get("primary_matched_card_title"),
                    confidence_level=state.get("confidence_level"),
                )
            except Exception as exc:
                logger.warning("保存企微问答会话上下文失败，不影响主流程：%s", exc)

        return MockWeComResponse(
            message_id=message.message_id,
            reply=answer,
            command=CommandType.NORMAL_QUESTION.value,
            session_active=False,
            run_id=state.get("run_id"),
            status=state.get("status"),
        )
