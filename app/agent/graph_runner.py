"""AskGraphRunner：注入 Session 后执行 LangGraph。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agent.ask_state import AskState
from app.agent.workflow import get_compiled_ask_graph
from app.observability.trace_service import TraceService


class AskGraphRunner:
    """每次请求独立运行 compiled graph，可选接入 LangSmith tracing。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._trace_service = TraceService()

    def run(self, state: AskState) -> AskState:
        """执行 LangGraph；开启 LangSmith 时走 TraceService.invoke_graph。"""
        graph = get_compiled_ask_graph()
        if self._trace_service.is_enabled():
            return self._trace_service.invoke_graph(graph, state, self.session)
        config = {"configurable": {"db": self.session}}
        return graph.invoke(state, config)
