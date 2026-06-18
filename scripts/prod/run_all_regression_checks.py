#!/usr/bin/env python
"""一键回归：阶段 2～6 检查脚本汇总。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = "docs/prod/.env"
PYTHON = sys.executable


@dataclass
class Step:
    name: str
    script: str
    args: list[str]
    skip_on_fast: bool = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="阶段 2～6 一键回归")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    parser.add_argument("--fast", action="store_true", help="跳过 LLM/RAG 等耗时真实调用")
    return parser.parse_args()


def _steps(env_file: str) -> list[Step]:
    ef = ["--env-file", env_file]
    return [
        Step("配置检查", "check_prod_config.py", []),
        Step("AI 基础设施", "check_ai_infra.py", ef + ["--checks", "all"], skip_on_fast=True),
        Step("RAG V2", "check_rag_v2.py", ef + ["--question", "客户登录失败并提示账号无权限时如何排查？"], skip_on_fast=True),
        Step("模拟企微沉淀", "check_mock_wecom_deposit.py", ef, skip_on_fast=True),
        Step("Stage4 补充", "check_stage4_supplement.py", ef),
        Step("Stage4 反馈闭环", "check_enhance_stage4_feedback_loop.py", ef),
        Step("Stage5 后台审核", "check_stage5_admin_review.py", ef),
        Step("Stage5 审核流", "check_stage5_review_flow.py", ef, skip_on_fast=True),
        Step("Stage5 补充", "check_stage5_supplement.py", ef, skip_on_fast=True),
        Step("Stage6 安全扫描", "check_stage6_security.py", ef),
        Step("Stage6 幂等", "check_stage6_idempotency.py", ef, skip_on_fast=True),
        Step("向量任务统计", "check_vector_tasks.py", ef),
    ]


def _run_step(step: Step, env_file: str) -> tuple[bool, str]:
    script_path = PROJECT_ROOT / "scripts" / "prod" / step.script
    if not script_path.is_file():
        return False, f"脚本不存在：{step.script}"

    cmd = [PYTHON, str(script_path), *step.args]
    if step.script == "check_prod_config.py":
        cmd = [PYTHON, str(script_path), "--env-file", env_file]

    try:
        proc = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "执行超时"

    output = (proc.stdout or "") + (proc.stderr or "")
    tail = "\n".join(output.strip().splitlines()[-5:]) if output.strip() else "(无输出)"
    ok = proc.returncode == 0
    return ok, tail


def main() -> int:
    args = parse_args()
    steps = _steps(args.env_file)

    print("=" * 60)
    print("阶段 2～6 一键回归")
    print(f"env-file: {args.env_file}")
    print(f"fast模式: {args.fast}")
    print("=" * 60)

    rows: list[tuple[str, str, str]] = []
    failed = 0

    for step in steps:
        if args.fast and step.skip_on_fast:
            rows.append((step.name, "SKIP", "fast 模式跳过"))
            print(f"[SKIP] {step.name}")
            continue

        ok, detail = _run_step(step, args.env_file)
        status = "PASS" if ok else "FAIL"
        rows.append((step.name, status, detail.replace("\n", " | ")[:120]))
        print(f"[{status}] {step.name}")
        if not ok:
            failed += 1
            print(f"       {detail}")

    print("-" * 60)
    print("汇总：")
    print(f"{'检查项':<20} {'结果':<8} 摘要")
    for name, status, detail in rows:
        print(f"{name:<20} {status:<8} {detail}")

    print("=" * 60)
    if failed:
        print(f"[结果] 失败：{failed} 项未通过")
        return 1
    print("[结果] 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
