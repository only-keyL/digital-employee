"""WeCom mock callback acceptance script for Phase 11."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings
from app.db.database import SessionLocal
from app.models.question_log import QuestionLog
from app.repositories.unanswered_repository import UnansweredRepository

HIT_QUESTION = "客户现场登录失败，提示账号无权限，应该怎么处理？"
DEDUP_QUESTION = HIT_QUESTION
MISS_QUESTION = "客户打印模板套打偏移怎么处理？"
HIT_MSG_ID = "mock-wecom-hit-001"
DEDUP_MSG_ID = "mock-wecom-dedup-001"
MISS_MSG_ID = "mock-wecom-miss-001"
EMPTY_MSG_ID = "mock-wecom-empty-001"


def _api_base_url() -> str:
    host = settings.app_host
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    return f"http://{host}:{settings.app_port}"


def _parse_xml_content(xml_text: str) -> str:
    root = ET.fromstring(xml_text)
    content_el = root.find("Content")
    if content_el is None or content_el.text is None:
        return ""
    return content_el.text.strip()


def _count_wecom_logs_for_question(question: str) -> int:
    with SessionLocal() as session:
        stmt = (
            select(func.count())
            .select_from(QuestionLog)
            .where(
                QuestionLog.source_type == "wecom",
                QuestionLog.question_raw == question,
            )
        )
        return int(session.scalar(stmt) or 0)


def _count_empty_wecom_logs() -> int:
    with SessionLocal() as session:
        stmt = (
            select(func.count())
            .select_from(QuestionLog)
            .where(
                QuestionLog.source_type == "wecom",
                func.trim(QuestionLog.question_raw) == "",
            )
        )
        return int(session.scalar(stmt) or 0)


def _mock_payload(
    *,
    msg_id: str,
    content: str,
    msg_type: str = "text",
) -> dict:
    return {
        "msg_id": msg_id,
        "from_user": "wecom_user_demo",
        "to_user": "corp_agent",
        "chat_id": "wecom_group_demo",
        "msg_type": msg_type,
        "content": content,
        "create_time": 1718000000,
    }


def main() -> int:
    base_url = _api_base_url()
    print(f"Checking WeCom mock callback against: {base_url}")

    try:
        with httpx.Client(timeout=60.0) as client:
            health_resp = client.get(f"{base_url}/api/health")
            health_resp.raise_for_status()
            if health_resp.json().get("status") != "ok":
                print(f"[FAIL] Health check status invalid: {health_resp.json()}")
                return 1

            verify_resp = client.get(
                f"{base_url}/api/wecom/callback",
                params={
                    "echostr": "mock_echo",
                    "timestamp": "1",
                    "nonce": "1",
                    "msg_signature": "any",
                },
            )
            verify_resp.raise_for_status()
            if verify_resp.text != "mock_echo":
                print(f"[FAIL] URL verify expected mock_echo, got: {verify_resp.text!r}")
                return 1
            print("[PASS] URL verify mock echo OK.")

            hit_resp = client.post(
                f"{base_url}/api/wecom/mock/callback",
                json=_mock_payload(msg_id=HIT_MSG_ID, content=HIT_QUESTION),
            )
            hit_resp.raise_for_status()
            content_type = hit_resp.headers.get("content-type", "")
            if "xml" not in content_type.lower():
                print(f"[FAIL] Hit response content-type expected xml, got: {content_type}")
                return 1

            hit_content = _parse_xml_content(hit_resp.text)
            if not hit_content:
                print("[FAIL] Hit XML Content is empty.")
                return 1
            if "答案来源" not in hit_content and "Mock 模型回答" not in hit_content:
                print(f"[FAIL] Hit XML Content missing answer marker: {hit_content[:200]}")
                return 1

            wecom_hit_count = _count_wecom_logs_for_question(HIT_QUESTION)
            if wecom_hit_count < 1:
                print("[FAIL] No question_log with source_type=wecom for hit question.")
                return 1
            print(f"[PASS] Hit mock callback OK (wecom logs={wecom_hit_count}).")

            dedup_resp_1 = client.post(
                f"{base_url}/api/wecom/mock/callback",
                json=_mock_payload(msg_id=DEDUP_MSG_ID, content=DEDUP_QUESTION),
            )
            dedup_resp_1.raise_for_status()
            dedup_content_1 = _parse_xml_content(dedup_resp_1.text)

            count_before_dedup = _count_wecom_logs_for_question(DEDUP_QUESTION)

            dedup_resp_2 = client.post(
                f"{base_url}/api/wecom/mock/callback",
                json=_mock_payload(msg_id=DEDUP_MSG_ID, content=DEDUP_QUESTION),
            )
            dedup_resp_2.raise_for_status()
            dedup_content_2 = _parse_xml_content(dedup_resp_2.text)

            if dedup_content_1 != dedup_content_2:
                print("[FAIL] Dedup XML Content mismatch on repeated msg_id.")
                return 1

            count_after_dedup = _count_wecom_logs_for_question(DEDUP_QUESTION)
            if count_after_dedup != count_before_dedup:
                print(
                    f"[FAIL] Dedup should not add question_log: before={count_before_dedup}, "
                    f"after={count_after_dedup}"
                )
                return 1
            print("[PASS] Dedup mock callback OK.")

            normalized_miss = MISS_QUESTION.strip()[:500]
            with SessionLocal() as session:
                repo = UnansweredRepository(session)
                record_before = repo.get_by_normalized(normalized_miss)
                freq_before = record_before.frequency if record_before else 0

            miss_resp = client.post(
                f"{base_url}/api/wecom/mock/callback",
                json=_mock_payload(msg_id=MISS_MSG_ID, content=MISS_QUESTION),
            )
            miss_resp.raise_for_status()
            miss_content = _parse_xml_content(miss_resp.text)
            if not miss_content:
                print("[FAIL] Miss XML Content is empty.")
                return 1

            miss_log_count = _count_wecom_logs_for_question(MISS_QUESTION)
            if miss_log_count < 1:
                print("[FAIL] Miss question should write question_log with source_type=wecom.")
                return 1

            with SessionLocal() as session:
                repo = UnansweredRepository(session)
                record_after = repo.get_by_normalized(normalized_miss)
                if record_after is None:
                    print("[FAIL] unanswered_question not found after wecom miss.")
                    return 1
                if record_before is None:
                    print(f"[PASS] unanswered_question created (frequency={record_after.frequency}).")
                elif record_after.frequency <= freq_before:
                    print(
                        f"[FAIL] Expected unanswered frequency to increase, "
                        f"before={freq_before}, after={record_after.frequency}"
                    )
                    return 1
                else:
                    print(f"[PASS] unanswered_question frequency increased to {record_after.frequency}.")
            print("[PASS] Miss mock callback OK.")

            empty_before = _count_empty_wecom_logs()
            empty_resp = client.post(
                f"{base_url}/api/wecom/mock/callback",
                json=_mock_payload(msg_id=EMPTY_MSG_ID, content=""),
            )
            empty_resp.raise_for_status()
            empty_content = _parse_xml_content(empty_resp.text)
            if "请输入有效问题" not in empty_content:
                print(f"[FAIL] Empty content reply unexpected: {empty_content}")
                return 1

            empty_after = _count_empty_wecom_logs()
            if empty_after != empty_before:
                print(
                    f"[FAIL] Empty content should not add empty question_log: "
                    f"before={empty_before}, after={empty_after}"
                )
                return 1
            print("[PASS] Empty content mock callback OK.")

        print("[PASS] WeCom mock check OK")
        return 0
    except httpx.HTTPError as exc:
        print(f"[FAIL] HTTP error: {exc}")
        return 1
    except Exception as exc:
        print(f"[FAIL] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
