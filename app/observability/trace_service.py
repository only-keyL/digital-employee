"""LangSmith 问答图追踪（阶段十）。"""

from __future__ import annotations

import contextlib
import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.agent.ask_state import AskState
from app.config.settings import Settings, get_settings
from app.observability.redaction import build_safe_metadata
from app.repositories.question_repository import QuestionRepository

logger = logging.getLogger(__name__)

_LANGCHAIN_ENV_KEYS = (
    "LANGCHAIN_TRACING_V2",
    "LANGCHAIN_API_KEY",
    "LANGCHAIN_PROJECT",
    "LANGCHAIN_ENDPOINT",
)


class TraceService:
    """LangSmith 追踪服务：包装问答图调用并回写 trace_id。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def is_enabled(self) -> bool:
        """是否已启用 LangSmith 追踪。"""
        return self._settings.is_langsmith_enabled

    def build_safe_metadata(self, state: AskState) -> dict[str, Any]:
        """从 AskState 构建可上报的安全元数据（无 PII）。"""
        return build_safe_metadata(state)

    def invoke_graph(self, graph: Any, state: AskState, session: Session) -> AskState:
        """执行问答图；启用追踪时附加 tracer 并持久化 trace_id。"""
        config = {"configurable": {"db": session}}
        if not self.is_enabled():
            return graph.invoke(state, config)

        trace_id: str | None = None
        try:
            result, trace_id = self._invoke_with_tracing(graph, state, config)
        except Exception as exc:
            logger.warning("LangSmith tracing failed, falling back to plain invoke: %s", exc)
            result = graph.invoke(state, config)

        question_log_id = result.get("question_log_id")
        if trace_id and question_log_id:
            self.persist_trace_id(session, int(question_log_id), trace_id)

        return result

    def _invoke_with_tracing(
        self,
        graph: Any,
        state: AskState,
        config: dict[str, Any],
    ) -> tuple[AskState, str | None]:
        from langchain_core.tracers.langchain import LangChainTracer
        from langsmith import Client

        metadata = self.build_safe_metadata(state)
        client = Client(
            api_key=self._settings.langsmith_api_key,
            api_url=self._settings.langsmith_endpoint or None,
            hide_inputs=self._settings.langsmith_hide_inputs,
            hide_outputs=self._settings.langsmith_hide_outputs,
        )
        tracer = LangChainTracer(
            project_name=self._settings.langsmith_project,
            client=client,
            metadata={k: str(v) for k, v in metadata.items()},
        )

        invoke_config = {
            **config,
            "callbacks": [tracer],
            "run_name": "digital_employee_ask",
            "metadata": metadata,
            "tags": ["digital-employee-assistant", "api-ask"],
        }

        with self._langchain_compat_env():
            result = graph.invoke(state, invoke_config)

        trace_id = self.extract_trace_id(tracer)
        return result, trace_id

    @contextlib.contextmanager
    def _langchain_compat_env(self):
        saved = {key: os.environ.get(key) for key in _LANGCHAIN_ENV_KEYS}
        try:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = self._settings.langsmith_api_key
            os.environ["LANGCHAIN_PROJECT"] = self._settings.langsmith_project
            if self._settings.langsmith_endpoint:
                os.environ["LANGCHAIN_ENDPOINT"] = self._settings.langsmith_endpoint
            else:
                os.environ.pop("LANGCHAIN_ENDPOINT", None)
            yield
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def extract_trace_id(self, tracer: Any) -> str | None:
        """从 LangChainTracer 中提取本次运行的 trace_id。"""
        try:
            run_map = getattr(tracer, "run_map", None) or {}
            for run in run_map.values():
                trace_id = getattr(run, "trace_id", None) or getattr(run, "id", None)
                if trace_id is not None:
                    return str(trace_id)

            latest_run = getattr(tracer, "latest_run", None)
            if latest_run is not None:
                trace_id = getattr(latest_run, "trace_id", None) or getattr(latest_run, "id", None)
                if trace_id is not None:
                    return str(trace_id)
        except Exception as exc:
            logger.warning("Failed to extract LangSmith trace id: %s", exc)
        return None

    def persist_trace_id(self, session: Session, question_log_id: int, trace_id: str) -> None:
        """将 LangSmith trace_id 写入 question_log 记录。"""
        try:
            QuestionRepository(session).update_langsmith_trace_id(question_log_id, trace_id)
            session.commit()
        except Exception as exc:
            logger.warning("Failed to persist langsmith_trace_id: %s", exc)
            try:
                session.rollback()
            except Exception:
                pass
