"""LangGraph ask workflow acceptance script for Phase 7."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings

HIT_QUESTION = "客户现场登录失败，提示账号无权限，应该怎么处理？"
MISS_QUESTION = "客户打印模板套打偏移怎么处理？"
EMPTY_QUESTION = "   "


def _api_base_url() -> str:
    host = settings.app_host
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    return f"http://{host}:{settings.app_port}"


def main() -> int:
    base_url = _api_base_url()
    health_url = f"{base_url}/api/health"
    ask_url = f"{base_url}/api/ask"
    print(f"Checking LangGraph ask workflow against: {base_url}")
    print(f"[INFO] LLM_PROVIDER={settings.llm_provider}")

    try:
        with httpx.Client(timeout=60.0) as client:
            health_resp = client.get(health_url)
            health_resp.raise_for_status()
            if health_resp.json().get("status") != "ok":
                print(f"[FAIL] Health check status invalid: {health_resp.json()}")
                return 1
            print("[PASS] Health check OK.")

            hit_resp = client.post(ask_url, json={"question": HIT_QUESTION, "source_type": "web"})
            hit_resp.raise_for_status()
            hit_data = hit_resp.json()
            answer = hit_data.get("answer") or ""

            if not hit_data.get("matched"):
                print(f"[FAIL] Hit question expected matched=true, got: {hit_data}")
                return 1
            if not hit_data.get("sources"):
                print(f"[FAIL] Hit question expected non-empty sources, got: {hit_data}")
                return 1
            if hit_data.get("question_log_id") is None:
                print(f"[FAIL] Hit question expected question_log_id, got: {hit_data}")
                return 1
            if not answer:
                print(f"[FAIL] Hit question expected non-empty answer, got: {hit_data}")
                return 1
            if "答案来源" not in answer:
                print(f"[FAIL] Hit answer missing 答案来源: {answer[:200]}")
                return 1
            if "阶段五模拟回答" in answer:
                print("[FAIL] Hit answer should not contain 阶段五模拟回答")
                return 1
            if settings.llm_provider.lower() == "mock" and "Mock 模型回答" not in answer:
                print("[FAIL] Mock mode answer should contain Mock 模型回答")
                return 1
            print("[PASS] Hit question graph flow OK.")

            miss_resp = client.post(ask_url, json={"question": MISS_QUESTION, "source_type": "web"})
            miss_resp.raise_for_status()
            miss_data = miss_resp.json()
            if miss_data.get("matched"):
                print(f"[FAIL] Miss question expected matched=false, got: {miss_data}")
                return 1
            if not miss_data.get("fallback_reason"):
                print(f"[FAIL] Miss question expected fallback_reason, got: {miss_data}")
                return 1
            if miss_data.get("question_log_id") is None:
                print(f"[FAIL] Miss question expected question_log_id, got: {miss_data}")
                return 1
            print("[PASS] Miss question graph flow OK.")

            empty_resp = client.post(ask_url, json={"question": EMPTY_QUESTION, "source_type": "web"})
            empty_resp.raise_for_status()
            empty_data = empty_resp.json()
            if empty_data.get("matched"):
                print(f"[FAIL] Empty question expected matched=false, got: {empty_data}")
                return 1
            if empty_data.get("question_log_id") is not None:
                print(f"[FAIL] Empty question expected question_log_id=null, got: {empty_data}")
                return 1
            fallback_reason = empty_data.get("fallback_reason") or ""
            if "问题不能为空" not in fallback_reason:
                print(f"[FAIL] Empty question expected fallback_reason containing 问题不能为空, got: {empty_data}")
                return 1
            print("[PASS] Empty question graph flow OK.")

    except Exception as exc:
        print(f"[FAIL] Graph check failed: {exc}")
        print("       Make sure the server is running:")
        print("       python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001")
        return 1

    print("[PASS] Graph check OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
