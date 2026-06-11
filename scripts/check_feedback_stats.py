"""Feedback and statistics acceptance script for Phase 9."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings

QUESTION_USEFUL = "阶段九测试：客户凭证过期后无法登录怎么办？"
QUESTION_USELESS = "阶段九测试：客户报表导出超时应该怎么处理？"
QUESTION_NEED_HUMAN = "阶段九测试：客户审批流卡住后如何手工放行？"


def _api_base_url() -> str:
    host = settings.app_host
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    return f"http://{host}:{settings.app_port}"


def _ask(client: httpx.Client, base_url: str, question: str) -> int:
    resp = client.post(f"{base_url}/api/ask", json={"question": question, "source_type": "web"})
    resp.raise_for_status()
    data = resp.json()
    log_id = data.get("question_log_id")
    if log_id is None:
        raise RuntimeError(f"question_log_id is null for question: {question}")
    return int(log_id)


def _submit_feedback(
    client: httpx.Client,
    base_url: str,
    *,
    question_log_id: int,
    feedback_type: str,
) -> dict:
    resp = client.post(
        f"{base_url}/api/feedback",
        json={
            "question_log_id": question_log_id,
            "feedback_type": feedback_type,
            "user_id": "check_feedback_stats",
        },
    )
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    base_url = _api_base_url()
    print(f"Checking feedback and statistics against: {base_url}")

    try:
        with httpx.Client(timeout=60.0) as client:
            health_resp = client.get(f"{base_url}/api/health")
            health_resp.raise_for_status()
            if health_resp.json().get("status") != "ok":
                print(f"[FAIL] Health check status invalid: {health_resp.json()}")
                return 1
            print("[PASS] Health check OK.")

            log_id_useful = _ask(client, base_url, QUESTION_USEFUL)
            print(f"[PASS] Ask #1 question_log_id={log_id_useful}.")

            useful_resp = _submit_feedback(
                client,
                base_url,
                question_log_id=log_id_useful,
                feedback_type="useful",
            )
            if not useful_resp.get("success"):
                print(f"[FAIL] useful feedback failed: {useful_resp}")
                return 1
            print("[PASS] useful feedback submitted.")

            duplicate_resp = _submit_feedback(
                client,
                base_url,
                question_log_id=log_id_useful,
                feedback_type="useless",
            )
            if duplicate_resp.get("success"):
                print(f"[FAIL] duplicate feedback should fail: {duplicate_resp}")
                return 1
            duplicate_message = duplicate_resp.get("message") or ""
            if "已提交" not in duplicate_message and "已反馈" not in duplicate_message:
                print(f"[FAIL] duplicate feedback message unexpected: {duplicate_resp}")
                return 1
            print("[PASS] duplicate feedback blocked.")

            log_id_useless = _ask(client, base_url, QUESTION_USELESS)
            useless_resp = _submit_feedback(
                client,
                base_url,
                question_log_id=log_id_useless,
                feedback_type="useless",
            )
            if not useless_resp.get("success"):
                print(f"[FAIL] useless feedback failed: {useless_resp}")
                return 1
            print("[PASS] useless feedback submitted.")

            log_id_need_human = _ask(client, base_url, QUESTION_NEED_HUMAN)
            need_human_resp = _submit_feedback(
                client,
                base_url,
                question_log_id=log_id_need_human,
                feedback_type="need_human",
            )
            if not need_human_resp.get("success"):
                print(f"[FAIL] need_human feedback failed: {need_human_resp}")
                return 1
            print("[PASS] need_human feedback submitted.")

            stats_resp = client.get(f"{base_url}/api/statistics/dashboard")
            stats_resp.raise_for_status()
            stats_payload = stats_resp.json()
            if not stats_payload.get("success"):
                print(f"[FAIL] statistics dashboard failed: {stats_payload}")
                return 1
            dashboard = stats_payload.get("data") or {}
            required_fields = [
                "total_questions",
                "match_rate",
                "miss_rate",
                "satisfaction_rate",
                "useful_feedback_count",
                "useless_feedback_count",
                "need_human_feedback_count",
                "top_negative_feedback_questions",
            ]
            for field in required_fields:
                if field not in dashboard:
                    print(f"[FAIL] dashboard missing field: {field}")
                    return 1
            if dashboard.get("useful_feedback_count", 0) < 1:
                print(f"[FAIL] useful_feedback_count expected >= 1, got: {dashboard}")
                return 1
            if dashboard.get("useless_feedback_count", 0) < 1:
                print(f"[FAIL] useless_feedback_count expected >= 1, got: {dashboard}")
                return 1
            if dashboard.get("need_human_feedback_count", 0) < 1:
                print(f"[FAIL] need_human_feedback_count expected >= 1, got: {dashboard}")
                return 1
            print("[PASS] statistics dashboard OK.")

            list_resp = client.get(f"{base_url}/api/feedback", params={"page_size": 50})
            list_resp.raise_for_status()
            list_payload = list_resp.json()
            if not list_payload.get("success"):
                print(f"[FAIL] feedback list failed: {list_payload}")
                return 1
            items = list_payload.get("data", {}).get("items", [])
            submitted_ids = {log_id_useful, log_id_useless, log_id_need_human}
            found_ids = {item.get("question_log_id") for item in items}
            if not submitted_ids.issubset(found_ids):
                print(f"[FAIL] feedback list missing submitted records: {found_ids}")
                return 1
            print("[PASS] feedback list contains submitted records.")

    except Exception as exc:
        print(f"[FAIL] Feedback stats check failed: {exc}")
        print("       Make sure the server is running:")
        print("       python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001")
        return 1

    print("[PASS] Feedback stats check OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
