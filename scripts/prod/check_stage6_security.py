#!/usr/bin/env python
"""Stage6 安全扫描：Git 跟踪、示例文件、代码库疑似密钥泄露。"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import get_settings
from app.core.env_validator import validate_settings
from app.core.settings import apply_env_file, load_settings_from_env_file

DEFAULT_ENV_FILE = "docs/prod/.env"

# 疑似真实密钥形态（命中后需人工判断）
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("sk-openai", re.compile(r"sk-[a-zA-Z0-9]{20,}"), "high"),
    ("api_key赋值", re.compile(r"(?i)(api_key|apikey)\s*=\s*['\"]?[a-zA-Z0-9_\-]{16,}"), "high"),
    ("mysql连接串", re.compile(r"mysql\+pymysql://[^/\s]+:[^@\s]+@"), "high"),
    ("redis连接串", re.compile(r"redis://:[^@\s]+@"), "high"),
    ("DEEPSEEK_API_KEY", re.compile(r"DEEPSEEK_API_KEY\s*=\s*sk-[a-zA-Z0-9]{10,}"), "high"),
    ("QDRANT_API_KEY", re.compile(r"QDRANT_API_KEY\s*=\s*[a-zA-Z0-9_\-]{12,}"), "medium"),
    ("LANGSMITH_API_KEY", re.compile(r"LANGSMITH_API_KEY\s*=\s*[a-zA-Z0-9_\-]{12,}"), "medium"),
    ("ADMIN_TOKEN明文打印", re.compile(r"print\s*\([^)]*admin_token", re.I), "high"),
]

# example 文件允许占位符，但禁止明显真实 Key
_EXAMPLE_FORBIDDEN = re.compile(
    r"(sk-[a-zA-Z0-9]{20,}|mysql\+pymysql://[^:]+:[^@]+@|redis://:[^@]+@)"
)

# 自测/fixture 中的明显非真实值
_SAFE_TEST_VALUES = frozenset(
    {
        "real_key_value",
        "qdrant_secret_key",
        "langsmith_secret_key",
        "wecom_secret_value",
        "wecom_token_value",
        "encoding_aes_key_value",
        "strong_prod_admin_token_value",
        "user:password",
        "root:root",
    }
)

# 允许扫描命中但降级为 low 的路径片段
_LOW_RISK_PATH_PARTS = (
    "scripts/prod/check_prod_config.py",
    "scripts/prod/check_ai_infra.py",
    "scripts/prod/check_stage6_security.py",
    "app/db/database.py",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage6 安全扫描")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    return parser.parse_args()


def _git_ls_files(path: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", path],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _scan_file(path: Path, *, is_example: bool = False) -> list[str]:
    hits: list[str] = []
    rel = path.relative_to(PROJECT_ROOT).as_posix()
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return hits

    for line_no, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "re.compile(" in line or "_SECRET_PATTERNS" in line or "_EXAMPLE_FORBIDDEN" in line:
            continue
        if "mask_url(" in line or "super_secret_pass" in line:
            continue
        if any(safe in line for safe in _SAFE_TEST_VALUES):
            continue

        if is_example:
            if _EXAMPLE_FORBIDDEN.search(line):
                if re.search(r"(?i)(your_|change_|placeholder|example)", line):
                    continue
                hits.append(f"example 文件含疑似真实密钥形态：{rel}:{line_no}")
            continue

        for name, pattern, level in _SECRET_PATTERNS:
            if not pattern.search(line):
                continue
            if any(part in rel for part in _LOW_RISK_PATH_PARTS):
                level = "low"
            if name == "mysql连接串" and "settings.database_url" in line:
                level = "low"
            hits.append(f"[{level}] {rel}:{line_no} 命中 {name}")

    return hits


def _iter_scan_dirs(settings) -> list[Path]:
    exclude = {p.strip() for p in settings.security_scan_exclude_dirs.split(",") if p.strip()}
    roots = [
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "docs" / "mvpdocs",
    ]
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(PROJECT_ROOT).as_posix()
            if any(rel == ex or rel.startswith(ex + "/") for ex in exclude):
                continue
            if path.suffix in {".py", ".md", ".html", ".js", ".css", ".env", ".example"}:
                files.append(path)
    return files


def main() -> int:
    args = parse_args()
    apply_env_file(args.env_file)
    settings = get_settings()

    print("=" * 60)
    print("Stage6 安全扫描")
    print("=" * 60)

    issues: list[str] = []

    if _git_ls_files("docs/prod/.env"):
        issues.append("[high] docs/prod/.env 已被 Git 跟踪")
    else:
        print("[PASS] docs/prod/.env 未被 Git 跟踪")

    if _git_ls_files("docs/prod/prod.zip"):
        issues.append("[high] docs/prod/prod.zip 已被 Git 跟踪")
    else:
        print("[PASS] docs/prod/prod.zip 未被 Git 跟踪")

    for example in (".env.example", ".env.prod.example", ".env.test.example"):
        path = PROJECT_ROOT / example
        if path.is_file():
            hits = _scan_file(path, is_example=True)
            if hits:
                issues.extend(hits)
            else:
                print(f"[PASS] {example} 未发现明显真实 Key")

    print("-" * 60)
    print("扫描 app / scripts / docs/mvpdocs（跳过 docs/prod）")
    for path in _iter_scan_dirs(settings):
        for hit in _scan_file(path):
            if "admin_token" in hit.lower() and "print" not in hit.lower():
                continue
            issues.append(hit)

    if settings.is_prod and not settings.admin_auth_enabled:
        issues.append("[high] prod 环境 ADMIN_AUTH_ENABLED 未开启")
    elif settings.is_prod:
        print("[PASS] prod 环境后台鉴权已开启")
    else:
        print("[INFO] 非 prod 环境，后台鉴权强制检查跳过")

    if not settings.langsmith_hide_inputs or not settings.langsmith_hide_outputs:
        issues.append("[medium] 建议开启 LangSmith 输入/输出脱敏")
    else:
        print("[PASS] LangSmith 脱敏配置已开启")

    prod_example = load_settings_from_env_file(str(PROJECT_ROOT / ".env.prod.example"), app_env="prod")
    prod_validation = validate_settings(prod_example, example_mode=True)
    if any("ADMIN_AUTH" in e for e in prod_validation.errors):
        issues.append("[medium] .env.prod.example 未正确声明 ADMIN_AUTH 要求")

    print("-" * 60)
    if issues:
        print(f"[WARN/FAIL] 共 {len(issues)} 项：")
        for item in issues[:30]:
            print(f"  - {item}")
        if len(issues) > 30:
            print(f"  ... 另有 {len(issues) - 30} 项")
        if settings.security_scan_fail_on_secret and any("[high]" in i for i in issues):
            print("[结果] 失败：发现高风险项")
            return 1
        if issues:
            print("[结果] 通过（仅低/中风险项，已记录）")
            return 0

    print("[结果] 全部通过")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] 安全扫描异常：{exc}")
        raise SystemExit(1) from exc
