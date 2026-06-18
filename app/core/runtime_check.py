"""FastAPI 启动阶段运行时配置检查。"""

from __future__ import annotations

import logging

from app.core.env_validator import ConfigCheckResult, validate_settings
from app.core.settings import Settings

logger = logging.getLogger(__name__)


class RuntimeConfigError(RuntimeError):
    """生产环境配置不合法，阻止服务启动。"""


def run_runtime_check(settings: Settings) -> None:
    """根据 APP_ENV 执行配置检查：dev/test 仅 warning，prod 有 error 则阻止启动。"""
    result = validate_settings(settings)
    _log_check_result(settings, result)

    if settings.is_prod and result.errors:
        message = "生产环境配置校验失败，服务拒绝启动：" + "；".join(result.errors)
        raise RuntimeConfigError(message)


def _log_check_result(settings: Settings, result: ConfigCheckResult) -> None:
    """以中文日志输出校验结果，敏感信息已在 safe_config 中脱敏。"""
    env_label = settings.app_env.upper()
    logger.info("开始运行时配置检查，当前环境：%s", env_label)

    for warning in result.warnings:
        logger.warning("[配置警告] %s", warning)

    for error in result.errors:
        if settings.is_prod:
            logger.error("[配置错误] %s", error)
        else:
            logger.warning("[配置提示] %s", error)

    if result.errors and settings.is_prod:
        logger.error("生产环境存在 %d 项配置错误，即将阻止启动。", len(result.errors))
    elif result.warnings:
        logger.info("配置检查完成：%d 条警告，服务继续启动。", len(result.warnings))
    else:
        logger.info("配置检查通过，未发现警告。")
