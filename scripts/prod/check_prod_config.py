#!/usr/bin/env python
"""生产配置检查脚本：校验 env 文件是否满足 dev / test / prod 边界要求。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.env_validator import validate_settings
from app.core.settings import Settings, load_settings_from_env_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="数字员工助手配置检查工具")
    parser.add_argument(
        "--env",
        choices=["dev", "test", "prod"],
        help="指定检查目标环境；未指定时使用 env 文件中的 APP_ENV",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="待检查的 env 文件路径，默认 .env",
    )
    parser.add_argument(
        "--example-mode",
        action="store_true",
        help="样例模式：检查 example 文件字段结构，并提示不可直接用于生产",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="运行内置自测用例",
    )
    return parser.parse_args()


def load_settings_for_check(env_file: str, app_env: str | None) -> Settings:
    """加载指定 env 文件；若文件不存在则回退到默认 Settings。"""
    path = Path(env_file)
    if not path.is_file():
        print(f"[WARN] env 文件不存在：{path}，将使用进程环境变量与默认值。")
        settings = Settings()
    else:
        settings = load_settings_from_env_file(str(path), app_env=app_env)
        return settings

    if app_env:
        payload = settings.model_dump()
        payload["app_env"] = app_env
        return Settings(**payload)
    return settings


def print_result(
    settings: Settings,
    result,
    *,
    example_mode: bool,
    env_file: str,
) -> int:
    """输出中文检查结果，返回进程退出码。"""
    print("=" * 60)
    print(f"配置检查环境：{settings.app_env.upper()}")
    print(f"配置文件：{env_file}")
    if example_mode:
        print("模式：example（样例配置通过不代表可生产启动）")
    print("-" * 60)

    if result.warnings:
        print(f"[警告] 共 {len(result.warnings)} 条：")
        for item in result.warnings:
            print(f"  - {item}")
    else:
        print("[警告] 无")

    if result.errors:
        print(f"[错误] 共 {len(result.errors)} 条：")
        for item in result.errors:
            print(f"  - {item}")
    else:
        print("[错误] 无")

    print("-" * 60)
    print("[安全配置快照]")
    print(json.dumps(result.safe_config, ensure_ascii=False, indent=2))
    print("=" * 60)

    if settings.is_prod and result.errors:
        print("[结果] 失败：生产配置存在错误。")
        return 1

    print("[结果] 通过：未发现阻止项。")
    return 0


def run_self_test() -> int:
    """内置自测：覆盖 prod 硬校验与 dev 宽容策略。"""
    cases: list[tuple[str, callable]] = [
        ("prod 使用 mock LLM 应失败", _case_prod_mock_llm_fails),
        ("prod 缺少 Qdrant API Key 应失败", _case_prod_missing_qdrant_key_fails),
        ("prod 使用 root 数据库账号应失败", _case_prod_root_db_fails),
        ("dev 缺少生产配置不应失败", _case_dev_missing_prod_config_ok),
    ]

    failed = 0
    print("=" * 60)
    print("配置检查脚本自测")
    print("=" * 60)

    for name, fn in cases:
        try:
            fn()
            print(f"[PASS] {name}")
        except AssertionError as exc:
            failed += 1
            print(f"[FAIL] {name} -> {exc}")

    print("-" * 60)
    if failed:
        print(f"自测失败：{failed}/{len(cases)}")
        return 1

    print(f"自测全部通过：{len(cases)}/{len(cases)}")
    return 0


def _case_prod_mock_llm_fails() -> None:
    settings = Settings(
        app_env="prod",
        llm_provider="mock",
        llm_api_key="real_key_value",
        qdrant_mode="remote",
        qdrant_url="https://qdrant.example.com",
        qdrant_api_key="qdrant_secret_key",
        qdrant_collection="digital_employee_knowledge_prod",
        redis_url="redis://127.0.0.1:6379/0",
        langsmith_tracing=True,
        langsmith_api_key="langsmith_secret_key",
        langsmith_project="digital-employee-prod",
        wecom_enabled=True,
        wecom_corp_id="corp123456",
        wecom_agent_id="1000001",
        wecom_secret="wecom_secret_value",
        wecom_token="wecom_token_value",
        wecom_encoding_aes_key="encoding_aes_key_value",
        mysql_user="dea_prod",
    )
    result = validate_settings(settings)
    assert result.errors, "prod + mock LLM 应产生 error"
    assert any("mock" in item.lower() for item in result.errors)


def _case_prod_missing_qdrant_key_fails() -> None:
    settings = Settings(
        app_env="prod",
        llm_provider="deepseek",
        llm_api_key="real_key_value",
        qdrant_mode="remote",
        qdrant_url="https://qdrant.example.com",
        qdrant_api_key="",
        qdrant_collection="digital_employee_knowledge_prod",
        redis_url="redis://127.0.0.1:6379/0",
        langsmith_tracing=True,
        langsmith_api_key="langsmith_secret_key",
        langsmith_project="digital-employee-prod",
        wecom_enabled=True,
        wecom_corp_id="corp123456",
        wecom_agent_id="1000001",
        wecom_secret="wecom_secret_value",
        wecom_token="wecom_token_value",
        wecom_encoding_aes_key="encoding_aes_key_value",
        mysql_user="dea_prod",
    )
    result = validate_settings(settings)
    assert result.errors, "prod 缺少 QDRANT_API_KEY 应产生 error"
    assert any("QDRANT_API_KEY" in item for item in result.errors)


def _case_prod_root_db_fails() -> None:
    settings = Settings(
        app_env="prod",
        llm_provider="deepseek",
        llm_api_key="real_key_value",
        qdrant_mode="remote",
        qdrant_url="https://qdrant.example.com",
        qdrant_api_key="qdrant_secret_key",
        qdrant_collection="digital_employee_knowledge_prod",
        redis_url="redis://127.0.0.1:6379/0",
        langsmith_tracing=True,
        langsmith_api_key="langsmith_secret_key",
        langsmith_project="digital-employee-prod",
        wecom_enabled=True,
        wecom_corp_id="corp123456",
        wecom_agent_id="1000001",
        wecom_secret="wecom_secret_value",
        wecom_token="wecom_token_value",
        wecom_encoding_aes_key="encoding_aes_key_value",
        mysql_user="root",
    )
    result = validate_settings(settings)
    assert result.errors, "prod + root 数据库账号应产生 error"
    assert any("root" in item.lower() for item in result.errors)


def _case_dev_missing_prod_config_ok() -> None:
    settings = Settings(
        app_env="dev",
        llm_provider="mock",
        qdrant_mode="local",
        redis_url="",
        langsmith_tracing=False,
        wecom_enabled=False,
        mysql_user="root",
    )
    result = validate_settings(settings)
    assert not result.errors, "dev 缺少生产配置不应产生 error"
    assert result.warnings, "dev 应至少输出 warning"


def main() -> int:
    args = parse_args()

    if args.self_test:
        return run_self_test()

    settings = load_settings_for_check(args.env_file, args.env)
    result = validate_settings(settings, example_mode=args.example_mode)
    return print_result(
        settings,
        result,
        example_mode=args.example_mode,
        env_file=args.env_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())
