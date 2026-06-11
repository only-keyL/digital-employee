"""Full ask flow acceptance script (Phase 4/5)."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings
from app.db.database import SessionLocal
from app.repositories.unanswered_repository import UnansweredRepository

HIT_QUESTION = "客户现场登录失败，提示账号无权限，应该怎么处理？"
MISS_QUESTION = "客户打印模板套打偏移怎么处理？"


def _api_base_url() -> str:
    host = settings.app_host
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    return f"http://{host}:{settings.app_port}"


def main() -> int:
    base_url = _api_base_url()
    health_url = f"{base_url}/api/health"
    ask_url = f"{base_url}/api/ask"
    print(f"Checking full flow against: {base_url}")

    try:
        with httpx.Client(timeout=10.0) as client:
            health_resp = client.get(health_url)
            health_resp.raise_for_status()
            health_payload = health_resp.json()
            if health_payload.get("status") != "ok":
                print(f"[FAIL] Health check status invalid: {health_payload}")
                return 1
            print("[PASS] Health check OK.")

            hit_resp = client.post(ask_url, json={"question": HIT_QUESTION, "source_type": "web"})
            hit_resp.raise_for_status()
            hit_data = hit_resp.json()
            if not hit_data.get("matched"):
                print(f"[FAIL] Hit question expected matched=true, got: {hit_data}")
                return 1
            if not hit_data.get("sources"):
                print(f"[FAIL] Hit question expected non-empty sources, got: {hit_data}")
                return 1
            if hit_data.get("question_log_id") is None:
                print(f"[FAIL] Hit question expected question_log_id, got: {hit_data}")
                return 1
            if not (hit_data.get("answer") or "").strip():
                print(f"[FAIL] Hit question expected non-empty answer, got: {hit_data}")
                return 1
            print("[PASS] Hit question flow OK.")

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
            print("[PASS] Miss question flow OK.")

            normalized = MISS_QUESTION.strip()[:500]
            with SessionLocal() as session:
                repo = UnansweredRepository(session)
                record = repo.get_by_normalized(normalized)
                if record is None:
                    print("[FAIL] unanswered_question record not found in database.")
                    return 1
                frequency_before = record.frequency
                print(f"[PASS] unanswered_question exists (frequency={frequency_before}).")

            repeat_resp = client.post(ask_url, json={"question": MISS_QUESTION, "source_type": "web"})
            repeat_resp.raise_for_status()

            with SessionLocal() as session:
                repo = UnansweredRepository(session)
                record = repo.get_by_normalized(normalized)
                if record is None:
                    print("[FAIL] unanswered_question missing after repeat ask.")
                    return 1
                if record.frequency <= frequency_before:
                    print(
                        f"[FAIL] Expected frequency to increase, before={frequency_before}, after={record.frequency}"
                    )
                    return 1
                print(f"[PASS] unanswered_question frequency increased to {record.frequency}.")

    except Exception as exc:
        print(f"[FAIL] Full flow check failed: {exc}")
        print("       Make sure the server is running:")
        print("       python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001")
        return 1

    print("[PASS] Full flow check OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
