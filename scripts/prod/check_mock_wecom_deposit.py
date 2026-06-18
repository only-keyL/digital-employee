#!/usr/bin/env python
"""Stage4 模拟企微沉淀链路验收脚本。"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.desensitize import sanitize_text
from app.core.settings import apply_env_file
from app.db.database import SessionLocal
from app.schemas.wecom_message_schema import WeComMessage
from app.services.deposit_session_service import DepositSessionService
from app.wecom.command_router import CommandRouter

DEFAULT_ENV_FILE = "docs/prod/.env"

# 完整测试卡片（唯一标题，避免与其他验收冲突）
FULL_CARD = """标题：Stage4验收专用知识卡片{suffix}
问题：Stage4验收时如何验证模拟企微沉淀链路是否正常工作？
答案：依次发送沉淀、模板、提交结构化卡片，并检查 contribution 与 pending 卡片是否生成。
系统：数字员工助手
模块：知识沉淀
标签：验收,沉淀,Stage4
场景：阶段4本地验收
原因分析：需要验证 CommandRouter 与 KnowledgeDepositGraph 全链路。
排查步骤：
1. 发送【沉淀】
2. 发送【模板】
3. 提交完整卡片
解决方案：按验收脚本逐步执行并核对数据库记录。
风险提示：验收数据需标记为测试用途。
来源群：验收测试群
来源人：check-script"""

INCOMPLETE_CARD = """标题：缺字段测试
问题：太短
答案：也短"""

DUPLICATE_CARD = """标题：登录失败提示账号无权限处理办法
问题：客户登录失败并提示账号无权限时如何排查？
答案：先确认账号是否启用，再检查角色权限、组织权限和菜单权限。
系统：业务系统
模块：登录权限
标签：登录,权限,账号
场景：客户无法登录
解决方案：补充分配角色和菜单权限后，让客户重新登录验证。"""

RISK_CARD = """标题：危险操作示例
问题：如何在生产环境快速清理所有业务数据？
答案：直接在生产库执行 drop table 和 truncate table 强制删除数据。
系统：业务系统
模块：数据库
标签：删除,生产
场景：误操作
解决方案：执行 drop table users; truncate table orders;
风险提示：无
来源群：测试群
来源人：tester"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="模拟企微沉淀验收")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    return parser.parse_args()


def _preview(text: str, n: int = 80) -> str:
    return sanitize_text(text or "", max_length=n)


async def _run_step(name: str, router: CommandRouter, session_svc: DepositSessionService, message: WeComMessage) -> bool:
    print(f"\n--- {name} ---")
    try:
        resp = await router.route(message)
        active = await session_svc.is_active(message)
        print(f"  command={resp.command}")
        print(f"  status={resp.status}")
        print(f"  session_active={active} (resp={resp.session_active})")
        print(f"  contribution_id={resp.contribution_id}")
        print(f"  knowledge_card_id={resp.knowledge_card_id}")
        print(f"  run_id={resp.run_id}")
        print(f"  reply={_preview(resp.reply)}")
        return True
    except Exception as exc:
        print(f"  [FAIL] {exc}")
        return False


async def main_async(env_file: str) -> int:
    apply_env_file(env_file)
    suffix = uuid.uuid4().hex[:8]
    group_id = f"check-group-{suffix}"
    user_id = f"check-user-{suffix}"

    def msg(content: str, mid: str | None = None) -> WeComMessage:
        return WeComMessage(
            message_id=mid or str(uuid.uuid4()),
            group_id=group_id,
            user_id=user_id,
            user_name="验收脚本",
            content=content,
        )

    results: dict[str, bool] = {}

    with SessionLocal() as db:
        router = CommandRouter(db)
        session_svc = DepositSessionService()

        # 1. 【沉淀】
        results["deposit_start"] = await _run_step("【沉淀】", router, session_svc, msg("【沉淀】"))
        active = await session_svc.is_active(msg(""))
        results["session_exists"] = active

        # 2. 【模板】
        results["template"] = await _run_step("【模板】", router, session_svc, msg("【模板】"))

        # 3. 缺字段卡片
        results["incomplete"] = await _run_step("缺字段卡片", router, session_svc, msg(INCOMPLETE_CARD))
        # 缺字段后 session 应保持
        results["session_after_incomplete"] = await session_svc.is_active(msg(""))

        # 4. 完整卡片
        full = FULL_CARD.format(suffix=suffix)
        results["full_card"] = await _run_step("完整卡片", router, session_svc, msg(full))

        # 5. 重新进入沉淀测重复
        await router.route(msg("【沉淀】"))
        results["duplicate"] = await _run_step("重复卡片", router, session_svc, msg(DUPLICATE_CARD))

        # 6. 重新进入沉淀测高风险
        await router.route(msg("【沉淀】"))
        results["risk"] = await _run_step("高风险卡片", router, session_svc, msg(RISK_CARD))

        # 7. 【取消沉淀】
        await router.route(msg("【沉淀】"))
        results["cancel"] = await _run_step("【取消沉淀】", router, session_svc, msg("【取消沉淀】"))
        results["session_cleared"] = not await session_svc.is_active(msg(""))

        # 8. 普通问题 AskGraphV2
        results["normal_question"] = await _run_step(
            "普通问题",
            router,
            session_svc,
            msg("客户登录失败并提示账号无权限时如何排查？"),
        )

    print("\n========== 验收汇总 ==========")
    all_ok = True
    for k, v in results.items():
        mark = "PASS" if v else "FAIL"
        print(f"  [{mark}] {k}")
        if not v:
            all_ok = False

    if all_ok:
        print("\n[PASS] 模拟企微沉淀验收全部通过")
        return 0
    print("\n[WARN] 部分验收项未通过，请检查上方输出")
    return 1


def main() -> int:
    args = parse_args()
    print("Stage4 模拟企微沉淀验收开始")
    return asyncio.run(main_async(args.env_file))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] 验收脚本异常：{exc}")
        raise SystemExit(1) from exc
