"""AskGraphRunner: invoke LangGraph with per-request Session injection."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agent.ask_state import AskState
from app.agent.workflow import get_compiled_ask_graph
from app.observability.trace_service import TraceService


class AskGraphRunner:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._trace_service = TraceService()

    def run(self, state: AskState) -> AskState:
        graph = get_compiled_ask_graph()
        if self._trace_service.is_enabled():
            return self._trace_service.invoke_graph(graph, state, self.session)
        config = {"configurable": {"db": self.session}}
        return graph.invoke(state, config)
