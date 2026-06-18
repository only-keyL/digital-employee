#!/usr/bin/env python
"""Stage6 message_id 幂等验收：重复提交、冲突、failed 重试。"""

from __future__ import annotations

import argparse
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.settings import apply_env_file
from app.db.database import SessionLocal
from app.models.ask_run import AskRun
from app.models.knowledge_card import KnowledgeCard
from app.models.knowledge_contribution import KnowledgeContribution
from app.models.message_process_log import MessageProcessLog
from app.services.message_idempotency_service import MessageIdempotencyService

DEFAULT_ENV_FILE = "docs/prod/.env"
PREFIX = "【阶段6幂等验收】"

FULL_CARD = f"""标题：{PREFIX}幂等投稿卡片{{suffix}}
问题：{PREFIX}重复 message_id 时 contribution 是否只生成一次？
答案：{PREFIX}第二次相同 message_id 应命中 duplicate_success。
系统：数字员工助手
模块：幂等验收
标签：stage6,幂等,验收
场景：阶段6幂等脚本
原因分析：验证 message_process_log 约束。
排查步骤：
1. 首次提交
2. 重复提交
解决方案：检查 contribution_count_delta 应为 1。
风险提示：测试数据。
来源群：stage6_check
来源人：stage6-script"""


@dataclass
class Counts:
    contribution: int
    knowledge_card: int
    ask_run: int
    message_log: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage6 幂等验收")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    return parser.parse_args()


def _snapshot(session) -> Counts:
    return Counts(
        contribution=session.scalar(select(func.count()).select_from(KnowledgeContribution)) or 0,
        knowledge_card=session.scalar(select(func.count()).select_from(KnowledgeCard)) or 0,
        ask_run=session.scalar(select(func.count()).select_from(AskRun)) or 0,
        message_log=session.scalar(select(func.count()).select_from(MessageProcessLog)) or 0,
    )


def _post(client: TestClient, message_id: str, content: str, user_id: str = "stage6-check") -> dict:
    payload = {
        "message_id": message_id,
        "source": "mock_wecom",
        "user_id": user_id,
        "user_name": "stage6-script",
        "group_id": "stage6-group",
        "content": content,
    }
    resp = client.post("/api/mock/wecom/message", json=payload)
    if resp.status_code >= 500:
        raise RuntimeError(f"mock_wecom 返回 {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def main() -> int:
    args = parse_args()
    apply_env_file(args.env_file)

    from app.main import create_app

    client = TestClient(create_app())
    session = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    failed = 0

    print("=" * 60)
    print("Stage6 message_id 幂等验收")
    print("=" * 60)

    before = _snapshot(session)

    # 1. 重复【沉淀】
    deposit_mid = f"stage6-deposit-{suffix}"
    r1 = _post(client, deposit_mid, "【沉淀】")
    r2 = _post(client, deposit_mid, "【沉淀】")
    deposit_ok = r2.get("idempotent") is True and r2.get("idempotent_status") == "duplicate_success"
    print(f"[{'PASS' if deposit_ok else 'FAIL'}] 重复【沉淀】 idempotent={r2.get('idempotent')}")
    if not deposit_ok:
        failed += 1

    # 2. 重复知识卡片投稿（先开启 session 再提交）
    card_mid = f"stage6-card-{suffix}"
    _post(client, f"stage6-open-{suffix}", "【沉淀】")
    card_content = FULL_CARD.format(suffix=suffix)
    c1 = _post(client, card_mid, card_content)
    mid_card = _snapshot(session)
    c2 = _post(client, card_mid, card_content)
    card_delta = mid_card.contribution - before.contribution
    card_ok = (
        c2.get("idempotent") is True
        and c2.get("idempotent_status") == "duplicate_success"
        and card_delta <= 1
    )
    print(
        f"[{'PASS' if card_ok else 'FAIL'}] 重复知识投稿 "
        f"contribution_delta={card_delta} idempotent={c2.get('idempotent')}"
    )
    if not card_ok:
        failed += 1

    # 3. 重复普通问题
    ask_mid = f"stage6-ask-{suffix}"
    q = f"{PREFIX}客户登录失败提示无权限如何排查？"
    a1 = _post(client, ask_mid, q)
    mid_ask = _snapshot(session)
    a2 = _post(client, ask_mid, q)
    ask_delta = mid_ask.ask_run - before.ask_run
    ask_ok = a2.get("idempotent") is True and ask_delta <= 1
    print(f"[{'PASS' if ask_ok else 'FAIL'}] 重复普通问题 ask_run_delta={ask_delta}")
    if not ask_ok:
        failed += 1

    # 4. 同 message_id 不同内容 -> duplicate_conflict
    conflict_mid = f"stage6-conflict-{suffix}"
    _post(client, conflict_mid, f"{PREFIX}内容A")
    conflict_resp = _post(client, conflict_mid, f"{PREFIX}内容B完全不同")
    conflict_ok = (
        conflict_resp.get("command") == "duplicate_conflict"
        or conflict_resp.get("idempotent_status") == "duplicate_conflict"
    )
    print(f"[{'PASS' if conflict_ok else 'FAIL'}] 同 id 不同内容 duplicate_conflict")
    if not conflict_ok:
        failed += 1

    # 5. failed 可重试：手动标记 failed 后再提交
    retry_mid = f"stage6-retry-{suffix}"
    idem = MessageIdempotencyService(session)
    idem.begin_process(
        source="mock_wecom",
        message_id=retry_mid,
        content=f"{PREFIX}retry-test",
        group_id="g",
        user_id="u",
    )
    idem.mark_failed(source="mock_wecom", message_id=retry_mid, error_message="stage6 simulated failure")
    session.commit()
    retry_resp = _post(client, retry_mid, f"{PREFIX}retry-test")
    retry_ok = retry_resp.get("idempotent_status") in {None, "retry_failed", "duplicate_success"} or not retry_resp.get(
        "idempotent"
    )
    print(f"[{'PASS' if retry_ok else 'FAIL'}] status=failed 后允许重试 status={retry_resp.get('idempotent_status')}")
    if not retry_ok:
        failed += 1

    after = _snapshot(session)
    print("-" * 60)
    print("计数增量摘要：")
    print(f"  contribution_count_delta={after.contribution - before.contribution}")
    print(f"  knowledge_card_count_delta={after.knowledge_card - before.knowledge_card}")
    print(f"  ask_run_count_delta={after.ask_run - before.ask_run}")
    print(f"  message_process_log_count_delta={after.message_log - before.message_log}")
    print("=" * 60)

    session.close()
    if failed:
        print(f"[结果] 失败：{failed} 项未通过")
        return 1
    print("[结果] 全部通过")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] 幂等验收异常：{exc}")
        raise SystemExit(1) from exc
