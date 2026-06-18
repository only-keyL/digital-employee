#!/usr/bin/env python
"""AI 基础设施检查脚本：验证 Redis / Qdrant / DeepSeek / LangSmith 连通性。"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.desensitize import mask_secret, mask_url, sanitize_dict
from app.core.settings import Settings, load_settings_from_env_file
from app.infra.qdrant_client import QdrantInfraClient
from app.services.infra_health_service import InfraHealthService

DEFAULT_ENV_FILE = "docs/prod/.env"

_ISSUE_LABELS = {
    "chinese_colon": "使用了中文冒号",
    "extra_spaces": "键或值两侧有多余空格",
    "unquoted_hash_in_value": "值中包含 # 但未加引号",
    "unclosed_double_quote": "双引号未闭合",
    "space_in_key": "键名包含空格",
    "invalid_key_name": "键名不符合 ENV 规范",
    "no_equals": "缺少等号，不是有效 KEY=VALUE",
    "export_prefix": "使用了 export 前缀（不兼容）",
    "empty_key": "键名为空",
    "duplicate_key": "重复键名",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="数字员工 AI 基础设施检查工具")
    parser.add_argument(
        "--env-file",
        default=DEFAULT_ENV_FILE,
        help=f"配置文件路径，默认 {DEFAULT_ENV_FILE}",
    )
    parser.add_argument(
        "--checks",
        default="all",
        choices=["redis", "qdrant", "llm", "langsmith", "all"],
        help="检查项：redis / qdrant / llm / langsmith / all",
    )
    parser.add_argument(
        "--allow-qdrant-write",
        action="store_true",
        help="允许 Qdrant 写入固定测试向量（需显式传入）",
    )
    parser.add_argument(
        "--check-env-format",
        action="store_true",
        help="检查 env 文件格式（不输出真实值）",
    )
    parser.add_argument(
        "--print-safe-config",
        action="store_true",
        help="输出脱敏后的关键配置加载结果",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="运行内置自测（不访问真实外部服务）",
    )
    return parser.parse_args()


def load_settings(env_file: str) -> Settings:
    path = Path(env_file)
    if not path.is_file():
        print(f"[ERROR] 配置文件不存在：{path}")
        raise SystemExit(2)
    return load_settings_from_env_file(str(path))


def _mask_snippet(text: str, max_len: int = 20) -> str:
    """脱敏片段，最多 20 字符。"""
    if not text:
        return ""
    if len(text) <= 4:
        return "***"
    head = text[: min(8, max_len - 3)]
    return head + "..."


def check_env_format(env_file: str) -> int:
    """逐行检查 env 文件格式，只输出变量名与问题类型。"""
    path = Path(env_file)
    if not path.is_file():
        print(f"[ERROR] 配置文件不存在：{path}")
        return 2

    lines = path.read_text(encoding="utf-8").splitlines()
    seen_keys: dict[str, int] = {}
    errors = 0
    warnings = 0

    print("=" * 60)
    print("ENV 格式检查（不输出真实值）")
    print("=" * 60)

    for i, raw in enumerate(lines, 1):
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        issues: list[str] = []
        key = ""
        val = ""

        if stripped.lower().startswith("export "):
            issues.append("export_prefix")
            stripped = stripped[7:].strip()

        if "=" not in stripped:
            issues.append("no_equals")
            print(f"L{i}: [错误] {_ISSUE_LABELS['no_equals']} | 片段={_mask_snippet(stripped)}")
            errors += 1
            continue

        key, _, val = stripped.partition("=")
        key = key.strip()
        val = val.strip()

        if not key:
            issues.append("empty_key")
        if "\uff1a" in line or "：" in key:
            issues.append("chinese_colon")
        if raw.startswith(" ") or raw.endswith(" ") or " = " in raw:
            issues.append("extra_spaces")
        if " " in key:
            issues.append("space_in_key")
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            issues.append("invalid_key_name")
        if val.count('"') % 2 == 1:
            issues.append("unclosed_double_quote")
        if "#" in val and not (val.startswith('"') or val.startswith("'")):
            issues.append("unquoted_hash_in_value")
        if "\\" in val and not val.startswith('"'):
            issues.append("unquoted_backslash")

        if key in seen_keys:
            issues.append("duplicate_key")
            print(f"L{i}: [警告] 重复键 {key!r}（首次出现在 L{seen_keys[key]}）")
            warnings += 1
        else:
            seen_keys[key] = i

        if issues:
            labels = "、".join(_ISSUE_LABELS.get(x, x) for x in issues)
            level = "错误" if any(x in {"no_equals", "empty_key", "unclosed_double_quote"} for x in issues) else "警告"
            print(f"L{i}: [{level}] 键={key!r} | {labels} | 值片段={_mask_snippet(val)}")
            if level == "错误":
                errors += 1
            else:
                warnings += 1
        else:
            print(f"L{i}: [通过] 键={key!r}")

    # dotenv 解析测试
    try:
        from dotenv import dotenv_values

        dotenv_values(path)
        print("-" * 60)
        print("[dotenv] 解析通过，无语法错误。")
    except Exception as exc:
        print("-" * 60)
        print(f"[dotenv] 解析失败：{exc}")
        errors += 1

    print("-" * 60)
    print(f"统计：错误 {errors}，警告 {warnings}")
    return 1 if errors else 0


def print_safe_config(settings: Settings) -> None:
    """输出关键配置的脱敏加载结果。"""

    def flag(value: str) -> str:
        return "已配置" if value and value.strip() else "未配置"

    def safe_url(value: str) -> str:
        if not value or not value.strip():
            return "无"
        masked = mask_url(value)
        # 进一步隐藏主机细节，仅保留协议与脱敏占位
        if "://" in masked:
            scheme = masked.split("://", 1)[0]
            return f"{scheme}://***"
        return "***"

    def safe_key(value: str) -> str:
        if not value or not value.strip():
            return "无"
        return "****" if len(value) <= 8 else f"{value[:2]}****"

    print("=" * 60)
    print("安全配置加载结果（脱敏）")
    print("=" * 60)
    print(f"APP_ENV={settings.app_env}")
    print(f"REDIS_URL={flag(settings.redis_url)}，{safe_url(settings.redis_url)}")
    print(f"QDRANT_MODE={settings.qdrant_mode}")
    print(f"QDRANT_URL={flag(settings.qdrant_url)}，{safe_url(settings.qdrant_url)}")
    print(f"QDRANT_API_KEY={flag(settings.qdrant_api_key)}，{safe_key(settings.qdrant_api_key)}")
    print(f"QDRANT_COLLECTION={settings.qdrant_collection}")
    print(f"LLM_PROVIDER={settings.llm_provider}")
    print(f"LLM_API_KEY={flag(settings.llm_api_key)}，{safe_key(settings.llm_api_key)}")
    print(f"LLM_MODEL={settings.llm_model}")
    print(f"LANGSMITH_TRACING={str(settings.langsmith_tracing).lower()}")
    print(f"LANGSMITH_API_KEY={flag(settings.langsmith_api_key)}，{safe_key(settings.langsmith_api_key)}")
    print(f"LANGSMITH_PROJECT={settings.langsmith_project}")
    print(f"LANGSMITH_ENDPOINT={flag(settings.langsmith_endpoint)}，{safe_url(settings.langsmith_endpoint)}")
    print("=" * 60)


def print_check(name: str, result: dict) -> None:
    status = result.get("status", "unknown")
    message = result.get("message", "")
    print(f"[{name.upper()}] status={status} | {message}")
    safe = sanitize_dict(result)
    print(json.dumps(safe, ensure_ascii=False, indent=2))


def is_failure(check_name: str, result: dict) -> bool:
    status = result.get("status")
    if check_name == "langsmith" and status in {"skipped", "disabled", "ok", "configured"}:
        return False
    if check_name == "llm" and status == "skipped":
        return False
    return status == "failed"


async def run_checks(
    settings: Settings,
    checks: str,
    allow_qdrant_write: bool,
) -> int:
    service = InfraHealthService(settings)
    exit_code = 0

    print("=" * 60)
    print(f"AI 基础设施检查 | APP_ENV={settings.app_env} | checks={checks}")
    print("配置文件：已加载（路径不在此输出）")
    print("=" * 60)

    targets = ["redis", "qdrant", "llm", "langsmith"] if checks == "all" else [checks]

    for name in targets:
        if name == "redis":
            result = await service.check_redis(deep=True)
        elif name == "qdrant":
            result = await service.check_qdrant(deep=True, allow_write=allow_qdrant_write)
        elif name == "llm":
            result = await service.check_llm(deep=True)
        else:
            result = await service.check_langsmith(deep=True)

        print_check(name, result)
        print("-" * 60)

        if is_failure(name, result):
            exit_code = 1
        elif name == "llm" and result.get("status") == "skipped":
            print("[INFO] LLM 为 mock 或未启用真实模型，已跳过。")

    print("[结果]", "失败" if exit_code else "通过")
    return exit_code


def run_self_test() -> int:
    """内置自测：验证脱敏与策略，不访问真实外部服务。"""
    cases: list[tuple[str, callable]] = [
        ("脱敏工具不会泄露完整 key", _case_mask_secret),
        ("Redis URL 密码会被隐藏", _case_mask_redis_url),
        ("prod 环境 Qdrant 写入需显式授权", _case_prod_qdrant_write_guard),
        ("DeepSeek mock 不会被当成真实模型通过", _case_llm_mock_skipped),
        ("LangSmith disabled 显示 skipped/disabled", _case_langsmith_disabled),
    ]
    failed = 0
    print("=" * 60)
    print("AI 基础设施检查脚本自测")
    print("=" * 60)
    for name, fn in cases:
        try:
            fn()
            print(f"[PASS] {name}")
        except AssertionError as exc:
            failed += 1
            print(f"[FAIL] {name} -> {exc}")
    print("-" * 60)
    return 1 if failed else 0


def _case_mask_secret() -> None:
    masked = mask_secret("sk-1234567890abcdef")
    assert "1234567890abcdef" not in masked
    assert "***" in masked


def _case_mask_redis_url() -> None:
    masked = mask_url("redis://:super_secret_pass@127.0.0.1:6379/0")
    assert "super_secret_pass" not in masked


def _case_prod_qdrant_write_guard() -> None:
    settings = Settings(app_env="prod", qdrant_mode="remote", qdrant_url="https://example.com")
    client = QdrantInfraClient(settings)
    try:
        client.upsert_test_point(allow_write=False)
        raise AssertionError("prod 未授权写入应失败")
    except Exception as exc:
        assert "allow-qdrant-write" in str(exc) or "显式" in str(exc)


def _case_llm_mock_skipped() -> None:
    async def _run() -> None:
        service = InfraHealthService(Settings(llm_provider="mock"))
        result = await service.check_llm(deep=True)
        assert result["status"] == "skipped"

    asyncio.run(_run())


def _case_langsmith_disabled() -> None:
    async def _run() -> None:
        service = InfraHealthService(Settings(langsmith_tracing=False))
        result = await service.check_langsmith(deep=True)
        assert result["status"] == "disabled"

    asyncio.run(_run())


def main() -> int:
    args = parse_args()
    if args.self_test:
        return run_self_test()

    if args.check_env_format:
        return check_env_format(args.env_file)

    if args.print_safe_config:
        settings = load_settings(args.env_file)
        print_safe_config(settings)
        return 0

    settings = load_settings(args.env_file)
    return asyncio.run(run_checks(settings, args.checks, args.allow_qdrant_write))


if __name__ == "__main__":
    raise SystemExit(main())
