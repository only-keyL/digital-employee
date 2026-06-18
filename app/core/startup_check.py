"""生产启动前补充自检（不发起外部调用）。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.core.settings import Settings

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def collect_startup_issues(settings: Settings) -> tuple[list[str], list[str]]:
    """收集 prod 启动前 error/warning；dev/test 仅返回 warning 类提示。"""
    errors: list[str] = []
    warnings: list[str] = []

    if settings.is_prod:
        if not settings.admin_auth_enabled:
            errors.append("生产环境必须开启 ADMIN_AUTH_ENABLED。")
        if not (settings.admin_token or "").strip():
            errors.append("生产环境必须配置 ADMIN_TOKEN。")
        if not settings.message_dedup_enabled:
            errors.append("生产环境必须开启 MESSAGE_DEDUP_ENABLED。")
        if settings.message_dedup_ttl_seconds < 3600:
            errors.append("生产环境 MESSAGE_DEDUP_TTL_SECONDS 不应小于 3600。")
        if not settings.langsmith_hide_inputs or not settings.langsmith_hide_outputs:
            warnings.append("建议开启 LANGSMITH_HIDE_INPUTS 与 LANGSMITH_HIDE_OUTPUTS 脱敏。")
        if _is_env_tracked_by_git("docs/prod/.env"):
            errors.append("docs/prod/.env 已被 Git 跟踪，存在密钥泄露风险。")
        if _is_env_tracked_by_git("docs/prod/prod.zip"):
            errors.append("docs/prod/prod.zip 已被 Git 跟踪，存在泄露风险。")
    else:
        if not settings.admin_auth_enabled:
            warnings.append("后台鉴权未开启（dev/test 允许，prod 必须开启）。")
        if not settings.message_dedup_enabled:
            warnings.append("消息幂等未开启（dev/test 允许，prod 必须开启）。")

    return errors, warnings


def _is_env_tracked_by_git(relative_path: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", relative_path],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
