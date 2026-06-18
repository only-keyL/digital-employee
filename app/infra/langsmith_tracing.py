"""LangSmith 基础设施 tracing 探测：仅上传脱敏固定测试内容。"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.config.settings import Settings

logger = logging.getLogger(__name__)

_PROBE_INPUT = "stage2_infra_check"
_PROBE_OUTPUT = "stage2_trace_ok"


class LangSmithInfraError(Exception):
    """LangSmith 基础设施探测失败。"""


def run_langsmith_probe(settings: Settings) -> dict[str, Any]:
    """执行一次 LangSmith 测试 trace，不上传真实业务内容。"""
    if not settings.langsmith_tracing:
        return {
            "status": "skipped",
            "reason": "LANGSMITH_TRACING=false，未启用追踪。",
        }

    if not settings.langsmith_api_key.strip():
        return {
            "status": "skipped",
            "reason": "未配置 LANGSMITH_API_KEY，跳过 LangSmith 探测。",
        }

    try:
        from langsmith import Client

        client = Client(
            api_key=settings.langsmith_api_key,
            api_url=settings.langsmith_endpoint or None,
        )
        # 先验证凭据可读
        try:
            client.list_projects(limit=1)
        except Exception as exc:
            raise LangSmithInfraError(f"LangSmith 认证失败：{exc}") from exc

        metadata = {
            "module": "digital_employee",
            "stage": "stage2",
            "env": settings.app_env,
        }
        run_id = uuid.uuid4()
        client.create_run(
            id=run_id,
            name="stage2_infra_probe",
            run_type="chain",
            inputs={"input": _PROBE_INPUT},
            outputs={"output": _PROBE_OUTPUT},
            project_name=settings.langsmith_project,
            extra={"metadata": metadata},
            end_time=None,
        )
        trace_id = str(run_id)
        logger.info("LangSmith 基础设施探测成功，project=%s", settings.langsmith_project)
        return {
            "status": "ok",
            "project": settings.langsmith_project,
            "trace_id": trace_id[:8] + "..." if len(trace_id) > 8 else trace_id,
        }
    except LangSmithInfraError:
        raise
    except Exception as exc:
        logger.error("LangSmith 基础设施探测失败，原因=%s", exc)
        raise LangSmithInfraError(f"LangSmith 探测失败：{exc}") from exc
