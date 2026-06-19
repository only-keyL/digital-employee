#!/usr/bin/env python
"""生产 V1 增强阶段 7：交付文档检查脚本。"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "docs" / "生产V1增强交付文档"
README = PROJECT_ROOT / "README.md"

REQUIRED_DOCS = [
    "00_增强版最终交付总览.md",
    "01_完整业务流程图.md",
    "02_系统架构设计.md",
    "03_核心模块职责说明.md",
    "04_问答调用链详解.md",
    "05_知识沉淀调用链详解.md",
    "06_反馈闭环调用链详解.md",
    "07_运营看板指标口径.md",
    "08_数据流转与核心表说明.md",
    "09_多轮追问与轻量记忆说明.md",
    "10_启动部署与环境变量说明.md",
    "11_最终验收与回归命令.md",
    "12_比赛演示脚本与讲解话术.md",
    "13_面试表达与项目亮点.md",
    "14_最终交付验收清单.md",
    "15_已知边界与后续优化.md",
]

_SECRET_PATTERNS = [
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "sk- 形态密钥"),
    (re.compile(r"(?i)DEEPSEEK_API_KEY\s*=\s*sk-"), "DeepSeek 真实 Key"),
    (re.compile(r"(?i)LANGCHAIN_API_KEY\s*=\s*[a-zA-Z0-9_-]{20,}"), "LangChain 真实 Key"),
    (re.compile(r"mysql\+pymysql://[^:]+:[^@]+@"), "MySQL 连接串含密码"),
    (re.compile(r"(?i)password\s*=\s*[^\s#]{6,}"), "password= 疑似真实密码"),
]

_ALLOWED_PLACEHOLDER = re.compile(r"(?i)(your_|change_|placeholder|示例|占位|<|>|xxx)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="增强阶段7 交付文档检查")
    return parser.parse_args()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _scan_secrets(path: Path) -> list[str]:
    hits: list[str] = []
    for i, line in enumerate(_read(path).splitlines(), 1):
        if line.strip().startswith("#"):
            continue
        if _ALLOWED_PLACEHOLDER.search(line):
            continue
        for pattern, label in _SECRET_PATTERNS:
            if pattern.search(line):
                hits.append(f"{path.name}:{i} 疑似 {label}")
    return hits


def main() -> int:
    _ = parse_args()
    print("=" * 60)
    print("增强阶段7 交付文档检查")
    print("=" * 60)

    failed = 0

    if DOCS_DIR.is_dir():
        print("[PASS] 增强交付文档目录存在")
    else:
        print("[FAIL] 失败项：增强交付文档目录")
        print("失败原因：docs/生产V1增强交付文档/ 不存在")
        return 1

    missing = [name for name in REQUIRED_DOCS if not (DOCS_DIR / name).is_file()]
    if missing:
        print("[FAIL] 失败项：增强交付文档数量")
        print(f"失败原因：缺少 {len(missing)} 篇：{', '.join(missing)}")
        failed += 1
    else:
        print("[PASS] 16 篇增强交付文档齐全")

    if not README.is_file():
        print("[FAIL] 失败项：README")
        print("失败原因：README.md 不存在")
        return 1

    readme = _read(README)
    if "生产 V1 增强版状态" in readme or "生产V1增强版状态" in readme:
        print("[PASS] README 增强版状态存在")
    else:
        print("[FAIL] 失败项：README 增强版状态")
        print("失败原因：README 未包含「生产 V1 增强版状态」")
        failed += 1

    if "生产V1增强交付文档" in readme:
        print("[PASS] README 文档索引存在")
    else:
        print("[FAIL] 失败项：README 文档索引")
        print("失败原因：README 未包含生产V1增强交付文档索引")
        failed += 1

    mermaid_count = sum(1 for name in REQUIRED_DOCS if "```mermaid" in _read(DOCS_DIR / name))
    if mermaid_count >= 3:
        print("[PASS] Mermaid 图检查通过")
    else:
        print("[FAIL] 失败项：Mermaid 图")
        print(f"失败原因：仅 {mermaid_count} 篇含 Mermaid，至少需要 3 篇")
        failed += 1

    acceptance_doc = DOCS_DIR / "11_最终验收与回归命令.md"
    acceptance_text = _read(acceptance_doc) if acceptance_doc.is_file() else ""
    stage_scripts = [
        "check_enhance_stage1_logs.py",
        "check_enhance_stage2_trusted_answer.py",
        "check_enhance_stage3_duplicate_check.py",
        "check_enhance_stage4_feedback_loop.py",
        "check_enhance_stage5_operation_dashboard.py",
        "check_enhance_stage6_context_memory.py",
    ]
    if all(script in acceptance_text for script in stage_scripts):
        print("[PASS] 最终验收命令检查通过")
    else:
        print("[FAIL] 失败项：最终验收命令")
        print("失败原因：11_最终验收与回归命令.md 未包含阶段1～6全部验收脚本")
        failed += 1

    demo_doc = DOCS_DIR / "12_比赛演示脚本与讲解话术.md"
    demo_text = _read(demo_doc) if demo_doc.is_file() else ""
    demo_keywords = ["运营看板", "多轮追问", "反馈闭环", "重复检测"]
    if all(k in demo_text for k in demo_keywords):
        print("[PASS] 演示脚本关键词检查通过")
    else:
        print("[FAIL] 失败项：演示脚本关键词")
        print("失败原因：12_比赛演示脚本与讲解话术.md 缺少必要关键词")
        failed += 1

    interview_doc = DOCS_DIR / "13_面试表达与项目亮点.md"
    interview_text = _read(interview_doc) if interview_doc.is_file() else ""
    if "为什么用 LangGraph" in interview_text and "为什么用 Qdrant" in interview_text:
        print("[PASS] 面试表达关键词检查通过")
    else:
        print("[FAIL] 失败项：面试表达关键词")
        print("失败原因：13_面试表达与项目亮点.md 缺少 LangGraph / Qdrant 说明")
        failed += 1

    secret_hits: list[str] = []
    for name in REQUIRED_DOCS:
        path = DOCS_DIR / name
        if path.is_file():
            secret_hits.extend(_scan_secrets(path))
    if secret_hits:
        print("[FAIL] 失败项：疑似敏感信息")
        for hit in secret_hits[:8]:
            print(f"失败原因：{hit}")
        failed += 1
    else:
        print("[PASS] 疑似敏感信息检查通过")

    print("-" * 60)
    if failed:
        print("[FAIL] 阶段7文档验收未通过")
        return 1
    print("[PASS] 阶段7文档验收通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
