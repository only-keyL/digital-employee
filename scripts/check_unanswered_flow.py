"""未命中问题沉淀闭环验收脚本（阶段八）。

验证 generate-draft、convert、ignore 等未命中问题处理流程。
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings

# 用于 convert 流程测试的未命中问题
CONVERT_QUESTION = "阶段八测试：客户打印模板套打整体向右偏移应该怎么处理？"
# 用于 ignore 流程测试的未命中问题
IGNORE_QUESTION = "阶段八测试：客户报表导出超时应该怎么处理？"


def _api_base_url() -> str:
    """根据配置拼出本地 API 基址。"""
    host = settings.app_host
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    return f"http://{host}:{settings.app_port}"


def _find_pending_by_question(client: httpx.Client, base_url: str, question: str) -> dict | None:
    """在 pending 列表中按问题原文查找未命中记录。"""
    resp = client.get(f"{base_url}/api/unanswered-questions", params={"status": "pending", "page_size": 100})
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        raise RuntimeError(payload.get("message") or "list unanswered failed")
    for item in payload.get("data", {}).get("items", []):
        if (item.get("question") or "").strip() == question.strip():
            return item
    return None


def main() -> int:
    """执行未命中沉淀闭环验收，返回进程退出码。"""
    base_url = _api_base_url()
    health_url = f"{base_url}/api/health"
    ask_url = f"{base_url}/api/ask"
    print(f"Checking unanswered沉淀闭环 against: {base_url}")

    try:
        with httpx.Client(timeout=60.0) as client:
            health_resp = client.get(health_url)
            health_resp.raise_for_status()
            if health_resp.json().get("status") != "ok":
                print(f"[FAIL] Health check status invalid: {health_resp.json()}")
                return 1
            print("[PASS] Health check OK.")

            ask_convert = client.post(ask_url, json={"question": CONVERT_QUESTION, "source_type": "web"})
            ask_convert.raise_for_status()
            ask_convert_data = ask_convert.json()
            if ask_convert_data.get("matched"):
                print(f"[FAIL] Convert test question expected matched=false, got: {ask_convert_data}")
                return 1
            print("[PASS] Convert test question created via /api/ask.")

            pending = _find_pending_by_question(client, base_url, CONVERT_QUESTION)
            if pending is None:
                print("[FAIL] Pending unanswered record not found for convert test question.")
                return 1
            unanswered_id = pending["id"]
            print(f"[PASS] Found pending unanswered id={unanswered_id}.")

            draft_resp = client.post(f"{base_url}/api/unanswered-questions/{unanswered_id}/generate-draft")
            draft_resp.raise_for_status()
            draft_payload = draft_resp.json()
            if not draft_payload.get("success"):
                print(f"[FAIL] generate-draft failed: {draft_payload}")
                return 1
            draft_data = draft_payload.get("data") or {}
            for field in ("title", "question", "answer"):
                if not (draft_data.get(field) or "").strip():
                    print(f"[FAIL] generate-draft missing {field}: {draft_data}")
                    return 1
            print("[PASS] generate-draft preview OK.")

            convert_body = {
                "title": draft_data.get("title"),
                "question": draft_data.get("question"),
                "answer": draft_data.get("answer"),
                "system_name": draft_data.get("system_name") or "",
                "module_name": draft_data.get("module_name") or "",
                "tags": draft_data.get("tags") or "阶段八测试",
                "troubleshooting_steps": draft_data.get("troubleshooting_steps") or "",
                "solution": draft_data.get("solution") or "",
                "risk_notice": draft_data.get("risk_notice") or "",
                "source_group": "未命中沉淀",
                "source_user": "admin",
            }
            convert_resp = client.post(
                f"{base_url}/api/unanswered-questions/{unanswered_id}/convert",
                json=convert_body,
            )
            convert_resp.raise_for_status()
            convert_payload = convert_resp.json()
            if not convert_payload.get("success"):
                print(f"[FAIL] convert failed: {convert_payload}")
                return 1
            convert_data = convert_payload.get("data") or {}
            card_id = convert_data.get("convert_card_id") or convert_data.get("knowledge_card_id")
            if not card_id:
                print(f"[FAIL] convert missing card id: {convert_payload}")
                return 1
            print(f"[PASS] convert to draft OK, card_id={card_id}.")

            detail_resp = client.get(f"{base_url}/api/unanswered-questions/{unanswered_id}")
            detail_resp.raise_for_status()
            detail_payload = detail_resp.json()
            if not detail_payload.get("success"):
                print(f"[FAIL] get unanswered detail failed: {detail_payload}")
                return 1
            if detail_payload.get("data", {}).get("status") != "converted":
                print(f"[FAIL] expected status=converted, got: {detail_payload}")
                return 1
            print("[PASS] unanswered status=converted.")

            card_resp = client.get(f"{base_url}/api/knowledge-cards/{card_id}")
            card_resp.raise_for_status()
            card_payload = card_resp.json()
            if not card_payload.get("success"):
                print(f"[FAIL] get knowledge card failed: {card_payload}")
                return 1
            if card_payload.get("data", {}).get("audit_status") != "draft":
                print(f"[FAIL] expected audit_status=draft, got: {card_payload}")
                return 1
            print("[PASS] knowledge card audit_status=draft.")

            ask_ignore = client.post(ask_url, json={"question": IGNORE_QUESTION, "source_type": "web"})
            ask_ignore.raise_for_status()
            if ask_ignore.json().get("matched"):
                print(f"[FAIL] Ignore test question expected matched=false")
                return 1

            ignore_pending = _find_pending_by_question(client, base_url, IGNORE_QUESTION)
            if ignore_pending is None:
                print("[FAIL] Pending unanswered record not found for ignore test question.")
                return 1
            ignore_id = ignore_pending["id"]

            ignore_resp = client.post(f"{base_url}/api/unanswered-questions/{ignore_id}/ignore")
            ignore_resp.raise_for_status()
            ignore_payload = ignore_resp.json()
            if not ignore_payload.get("success"):
                print(f"[FAIL] ignore failed: {ignore_payload}")
                return 1
            if ignore_payload.get("data", {}).get("status") != "ignored":
                print(f"[FAIL] expected status=ignored, got: {ignore_payload}")
                return 1
            print("[PASS] ignore flow OK.")

    except Exception as exc:
        print(f"[FAIL] Unanswered flow check failed: {exc}")
        print("       Make sure the server is running:")
        print("       python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001")
        return 1

    print("[PASS] Unanswered flow check OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
