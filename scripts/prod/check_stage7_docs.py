#!/usr/bin/env python
"""Stage7 交付文档检查：文件齐全、README 索引、疑似泄密、Mermaid、Git 跟踪。"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "docs" / "生产V1交付文档"
README = PROJECT_ROOT / "README.md"

REQUIRED_DOCS = [
    "00_文档总览.md",
    "01_项目交付总览.md",
    "02_业务流程说明.md",
    "03_系统架构与模块职责.md",
    "04_核心调用链.md",
    "05_数据流转说明.md",
    "06_数据库表与状态流转.md",
    "07_接口清单.md",
    "08_本地启动指南.md",
    "09_测试环境部署指南.md",
    "10_运维与回归验收指南.md",
    "11_安全鉴权幂等审计说明.md",
    "12_真实企微接入前置说明.md",
    "13_演示脚本与讲解话术.md",
    "14_面试项目表达材料.md",
    "15_最终验收清单.md",
]

# 疑似真实密钥（允许占位符 your_ / change_ / 示例文字）
_SECRET_PATTERNS = [
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "OpenAI/类似 sk- Key"),
    (re.compile(r"mysql\+pymysql://[^:]+:[^@]+@"), "MySQL 连接串含密码"),
    (re.compile(r"redis://:[^@\s]+@"), "Redis 含密码"),
    (re.compile(r"(?i)DEEPSEEK_API_KEY\s*=\s*sk-"), "DeepSeek 真实 Key 形态"),
]

_ALLOWED_PLACEHOLDER = re.compile(r"(?i)(your_|change_|placeholder|示例|占位)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage7 交付文档检查")
    return parser.parse_args()


def _git_tracked(relative: str) -> bool:
    try:
        r = subprocess.run(
            ["git", "ls-files", "--error-unmatch", relative],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _scan_file_secrets(path: Path) -> list[str]:
    hits: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return [f"无法读取：{path.name}"]
    for i, line in enumerate(lines, 1):
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
    print("Stage7 交付文档检查")
    print("=" * 60)

    failed = 0

    # 1. 文档存在
    missing = [name for name in REQUIRED_DOCS if not (DOCS_DIR / name).is_file()]
    if missing:
        print(f"[FAIL] 缺少文档 {len(missing)} 个：")
        for m in missing:
            print(f"  - {m}")
        failed += 1
    else:
        print(f"[PASS] 16 个交付文档齐全")

    # 2. README 索引
    if not README.is_file():
        print("[FAIL] README.md 不存在")
        failed += 1
    else:
        readme_text = README.read_text(encoding="utf-8", errors="ignore")
        if "生产V1交付文档" in readme_text or "00_文档总览" in readme_text:
            print("[PASS] README 包含交付文档索引")
        else:
            print("[FAIL] README 缺少交付文档索引")
            failed += 1

    # 3. Mermaid
    no_mermaid: list[str] = []
    need_mermaid = ("02_", "03_", "12_")
    for name in REQUIRED_DOCS:
        if not any(name.startswith(p) for p in need_mermaid):
            continue
        text = (DOCS_DIR / name).read_text(encoding="utf-8", errors="ignore")
        if "```mermaid" not in text:
            no_mermaid.append(name)
    if no_mermaid:
        print(f"[FAIL] 缺少 Mermaid：{', '.join(no_mermaid)}")
        failed += 1
    else:
        print("[PASS] 关键文档含 Mermaid 流程图")

    # 4. 疑似泄密（仅扫描交付文档目录，不读 docs/prod/.env）
    secret_hits: list[str] = []
    for name in REQUIRED_DOCS:
        path = DOCS_DIR / name
        if path.is_file():
            secret_hits.extend(_scan_file_secrets(path))
    if secret_hits:
        print(f"[FAIL] 文档疑似含真实密钥 {len(secret_hits)} 处：")
        for h in secret_hits[:10]:
            print(f"  - {h}")
        failed += 1
    else:
        print("[PASS] 交付文档未发现明显真实密钥")

    # 5. Git 跟踪
    if _git_tracked("docs/prod/.env"):
        print("[FAIL] docs/prod/.env 已被 Git 跟踪")
        failed += 1
    else:
        print("[PASS] docs/prod/.env 未被 Git 跟踪")

    if _git_tracked("docs/prod/prod.zip"):
        print("[FAIL] docs/prod/prod.zip 已被 Git 跟踪")
        failed += 1
    else:
        print("[PASS] docs/prod/prod.zip 未被 Git 跟踪")

    print("-" * 60)
    if failed:
        print(f"[结果] 失败：{failed} 项")
        return 1
    print("[结果] 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
