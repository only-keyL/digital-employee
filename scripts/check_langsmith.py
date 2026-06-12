"""LangSmith 可观测性验收脚本（阶段十）。

验证 tracing 关闭/开启时 question_log.langsmith_trace_id 的写入行为。
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings
from app.db.database import SessionLocal
from app.repositories.question_repository import QuestionRepository

# 用于触发问答并检查 trace_id 的测试问题
QUESTION = "阶段十测试：客户凭证过期后无法登录怎么办？"


def _api_base_url() -> str:
    """根据配置拼出本地 API 基址。"""
    host = settings.app_host
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    return f"http://{host}:{settings.app_port}"


def _get_trace_id_from_db(question_log_id: int) -> str | None:
    """从数据库读取指定 question_log 的 langsmith_trace_id。"""
    with SessionLocal() as session:
        repo = QuestionRepository(session)
        log = repo.get_log_by_id(question_log_id)
        if log is None:
            raise RuntimeError(f"question_log id={question_log_id} not found in database")
        return log.langsmith_trace_id


def _run_disabled_mode(client: httpx.Client, base_url: str) -> int:
    """验证 LangSmith 关闭时 trace_id 应为空。"""
    if settings.is_langsmith_enabled:
        print(
            "[SKIP] Disabled mode checks skipped because LANGSMITH_TRACING=true "
            "and LANGSMITH_API_KEY is set. Restart with tracing off for mode A."
        )
        return 0

    health_resp = client.get(f"{base_url}/api/health")
    health_resp.raise_for_status()
    if health_resp.json().get("status") != "ok":
        print(f"[FAIL] Health check status invalid: {health_resp.json()}")
        return 1

    ask_resp = client.post(
        f"{base_url}/api/ask",
        json={"question": QUESTION, "source_type": "web"},
    )
    ask_resp.raise_for_status()
    data = ask_resp.json()
    question_log_id = data.get("question_log_id")
    if question_log_id is None:
        print(f"[FAIL] question_log_id is null: {data}")
        return 1

    trace_id = _get_trace_id_from_db(int(question_log_id))
    if trace_id is not None:
        print(f"[FAIL] langsmith_trace_id should be null in disabled mode, got: {trace_id}")
        return 1

    print("[PASS] LangSmith check OK (disabled mode)")
    return 0


def _run_enabled_mode(client: httpx.Client, base_url: str) -> int:
    """验证 LangSmith 开启时 trace_id 应非空。"""
    if not settings.is_langsmith_enabled:
        print("[SKIP] Enabled mode checks skipped (LANGSMITH_TRACING=false or LANGSMITH_API_KEY empty).")
        return 0

    ask_resp = client.post(
        f"{base_url}/api/ask",
        json={"question": QUESTION, "source_type": "web"},
    )
    ask_resp.raise_for_status()
    data = ask_resp.json()
    question_log_id = data.get("question_log_id")
    if question_log_id is None:
        print(f"[FAIL] question_log_id is null: {data}")
        return 1

    trace_id = _get_trace_id_from_db(int(question_log_id))
    if not trace_id:
        print("[FAIL] langsmith_trace_id should be non-empty when tracing is enabled.")
        return 1

    print(f"[PASS] LangSmith check OK (enabled mode), trace_id={trace_id}")
    return 0


def main() -> int:
    """执行 LangSmith 可观测性验收，返回进程退出码。"""
    base_url = _api_base_url()
    print(f"Checking LangSmith observability against: {base_url}")
    print(
        f"LANGSMITH_TRACING={settings.langsmith_tracing}, "
        f"LANGSMITH_API_KEY={'set' if settings.langsmith_api_key else 'empty'}, "
        f"is_langsmith_enabled={settings.is_langsmith_enabled}"
    )

    try:
        with httpx.Client(timeout=60.0) as client:
            disabled_code = _run_disabled_mode(client, base_url)
            if disabled_code != 0:
                return disabled_code

            enabled_code = _run_enabled_mode(client, base_url)
            if enabled_code != 0:
                return enabled_code

        return 0
    except httpx.HTTPError as exc:
        print(f"[FAIL] HTTP error: {exc}")
        return 1
    except Exception as exc:
        print(f"[FAIL] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
