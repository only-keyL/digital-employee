"""配置合法性校验：只检查配置，不连接外部依赖，不启动服务。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from app.core.settings import Settings

# 生产环境禁止使用的弱 Admin Token
_WEAK_ADMIN_TOKENS = frozenset({"admin", "123456", "password", "change_me", "your_token"})

# 明显的占位符/示例值，prod 环境禁止使用
_PLACEHOLDER_VALUES = frozenset(
    {
        "",
        "xxx",
        "your_key",
        "change_me",
        "changeme",
        "placeholder",
        "example",
        "your-api-key",
        "your_api_key",
        "your-secret",
        "your_secret",
        "todo",
        "tbd",
    }
)

# 生产环境默认业务库名（test 环境不应直接使用）
_PROD_DATABASE_NAMES = frozenset({"digital_employee", "digital_employee_prod"})

_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "mysql_password",
        "database_url_override",
        "llm_api_key",
        "embedding_api_key",
        "qdrant_api_key",
        "langsmith_api_key",
        "wecom_secret",
        "wecom_token",
        "wecom_encoding_aes_key",
        "wecom_bot_key",
        "redis_url",
        "admin_token",
    }
)


@dataclass
class ConfigCheckResult:
    """结构化配置检查结果。"""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    safe_config: dict[str, Any] = field(default_factory=dict)

    @property
    def is_ok_for_startup(self) -> bool:
        """dev/test 允许 warning；prod 必须无 error。"""
        return len(self.errors) == 0


def validate_settings(settings: Settings, *, example_mode: bool = False) -> ConfigCheckResult:
    """校验 Settings 是否满足当前 APP_ENV 要求，返回脱敏后的安全配置快照。"""
    result = ConfigCheckResult()
    result.safe_config = build_safe_config(settings)

    if settings.is_prod:
        _validate_prod(settings, result, example_mode=example_mode)
    elif settings.is_test:
        _validate_test(settings, result, example_mode=example_mode)
    else:
        _validate_dev(settings, result, example_mode=example_mode)

    return result


def build_safe_config(settings: Settings) -> dict[str, Any]:
    """导出脱敏后的配置快照，供日志与脚本输出。"""
    raw = settings.model_dump()
    safe: dict[str, Any] = {}

    for key, value in raw.items():
        if key in _SENSITIVE_FIELD_NAMES:
            safe[key] = _mask_secret(value)
            continue
        safe[key] = value

    safe["database_url"] = _mask_database_url(settings.database_url)
    safe["effective_mysql_user"] = settings.effective_mysql_user
    safe["effective_mysql_database"] = settings.effective_mysql_database
    safe["is_dev"] = settings.is_dev
    safe["is_test"] = settings.is_test
    safe["is_prod"] = settings.is_prod
    return safe


def _validate_prod(settings: Settings, result: ConfigCheckResult, *, example_mode: bool) -> None:
    """生产环境硬校验：任一关键项缺失或违规即记录 error。"""
    if example_mode:
        result.warnings.append("当前为 example 模式：样例配置通过不代表可生产启动。")

    if settings.llm_provider.lower() == "mock":
        result.errors.append("生产环境禁止 LLM_PROVIDER=mock。")
    if not _is_configured(settings.llm_api_key):
        result.errors.append("生产环境必须配置 LLM_API_KEY。")
    elif _is_placeholder_value(settings.llm_api_key):
        result.errors.append("生产环境 LLM_API_KEY 不能使用占位符示例值。")

    if settings.qdrant_mode.lower() == "local":
        result.errors.append("生产环境禁止 QDRANT_MODE=local。")
    if not _is_configured(settings.qdrant_url):
        result.errors.append("生产环境必须配置 QDRANT_URL。")
    elif _is_placeholder_value(settings.qdrant_url):
        result.errors.append("生产环境 QDRANT_URL 不能使用占位符示例值。")
    if not _is_configured(settings.qdrant_api_key):
        result.errors.append("生产环境必须配置 QDRANT_API_KEY。")
    elif _is_placeholder_value(settings.qdrant_api_key):
        result.errors.append("生产环境 QDRANT_API_KEY 不能使用占位符示例值。")

    collection = settings.qdrant_collection.lower()
    if collection.endswith("_dev") or collection.endswith("_test"):
        result.errors.append("生产环境 QDRANT_COLLECTION 不允许使用 _dev 或 _test 后缀。")

    if not _is_configured(settings.redis_url):
        result.errors.append("生产环境必须配置 REDIS_URL。")
    elif _is_placeholder_value(settings.redis_url):
        result.errors.append("生产环境 REDIS_URL 不能使用占位符示例值。")

    if not settings.langsmith_tracing:
        result.errors.append("生产环境 LANGSMITH_TRACING 必须为 true。")
    if not _is_configured(settings.langsmith_api_key):
        result.errors.append("生产环境必须配置 LANGSMITH_API_KEY。")
    elif _is_placeholder_value(settings.langsmith_api_key):
        result.errors.append("生产环境 LANGSMITH_API_KEY 不能使用占位符示例值。")
    if not _is_configured(settings.langsmith_project):
        result.errors.append("生产环境必须配置 LANGSMITH_PROJECT。")
    elif _is_placeholder_value(settings.langsmith_project):
        result.errors.append("生产环境 LANGSMITH_PROJECT 不能使用占位符示例值。")

    if not settings.wecom_enabled:
        result.errors.append("生产环境 WECOM_ENABLED 必须为 true。")
    for value, label in (
        (settings.wecom_corp_id, "WECOM_CORP_ID"),
        (settings.wecom_agent_id, "WECOM_AGENT_ID"),
        (settings.wecom_secret, "WECOM_SECRET"),
        (settings.wecom_token, "WECOM_TOKEN"),
        (settings.wecom_encoding_aes_key, "WECOM_ENCODING_AES_KEY"),
    ):
        if not _is_configured(value):
            result.errors.append(f"生产环境必须配置 {label}。")
        elif _is_placeholder_value(value):
            result.errors.append(f"生产环境 {label} 不能使用占位符示例值。")

    if settings.effective_mysql_user.lower() == "root":
        result.errors.append("生产环境禁止使用 root 数据库账号。")

    if not settings.admin_auth_enabled:
        result.errors.append("生产环境 ADMIN_AUTH_ENABLED 必须为 true。")
    if not _is_configured(settings.admin_token):
        result.errors.append("生产环境必须配置 ADMIN_TOKEN。")
    elif settings.admin_token.strip().lower() in _WEAK_ADMIN_TOKENS:
        result.errors.append("生产环境 ADMIN_TOKEN 不能使用弱口令或占位符。")
    elif _is_placeholder_value(settings.admin_token):
        result.errors.append("生产环境 ADMIN_TOKEN 不能使用占位符示例值。")

    if not settings.message_dedup_enabled:
        result.errors.append("生产环境 MESSAGE_DEDUP_ENABLED 必须为 true。")
    if settings.message_dedup_ttl_seconds < 3600:
        result.errors.append("生产环境 MESSAGE_DEDUP_TTL_SECONDS 不应小于 3600。")

    _warn_if_obvious_placeholder(settings, result)


def _validate_test(settings: Settings, result: ConfigCheckResult, *, example_mode: bool) -> None:
    """测试环境：避免误用生产库/集合，允许 mock 与关闭 tracing。"""
    if example_mode:
        result.warnings.append("当前为 example 模式：仅校验字段结构，不代表测试环境已就绪。")

    db_name = settings.effective_mysql_database.lower()
    if db_name in _PROD_DATABASE_NAMES:
        result.warnings.append(
            "测试环境不建议直接使用生产数据库名 digital_employee，请使用独立测试库。"
        )

    collection = settings.qdrant_collection.lower()
    if collection.endswith("_prod") or collection == "knowledge_cards":
        result.warnings.append(
            "测试环境建议使用带 _test 后缀的 QDRANT_COLLECTION，避免污染生产集合。"
        )

    _append_dev_like_warnings(settings, result)


def _validate_dev(settings: Settings, result: ConfigCheckResult, *, example_mode: bool) -> None:
    """开发环境：允许 mock/local/关闭 tracing，仅输出 warning。"""
    if example_mode:
        result.warnings.append("当前为 example 模式：dev 样例仅用于字段结构参考。")

    _append_dev_like_warnings(settings, result)


def _append_dev_like_warnings(settings: Settings, result: ConfigCheckResult) -> None:
    """dev/test 共用：提示缺失的生产配置，但不阻止启动。"""
    if settings.llm_provider.lower() == "mock":
        result.warnings.append("当前使用 Mock LLM，仅适用于本地开发/测试。")

    if settings.qdrant_mode.lower() == "local":
        result.warnings.append("当前使用本地 Qdrant 模式，生产环境需切换为 remote。")

    if not settings.langsmith_tracing:
        result.warnings.append("LangSmith 追踪未启用。")

    if not settings.wecom_enabled:
        result.warnings.append("企业微信真实回调未启用。")

    if not _is_configured(settings.redis_url):
        result.warnings.append("未配置 REDIS_URL，二期 Redis 能力尚未接入。")

    if settings.effective_mysql_user.lower() == "root":
        result.warnings.append("当前数据库账号为 root，生产环境禁止使用。")


def _warn_if_obvious_placeholder(settings: Settings, result: ConfigCheckResult) -> None:
    """prod 额外扫描：任何关键字符串字段含明显占位符都记 warning。"""
    checks = {
        "LLM_BASE_URL": settings.llm_base_url,
        "QDRANT_URL": settings.qdrant_url,
        "LANGSMITH_PROJECT": settings.langsmith_project,
        "WECOM_CALLBACK_URL": settings.wecom_callback_url,
    }
    for label, value in checks.items():
        if _is_configured(value) and _is_placeholder_value(value):
            result.warnings.append(f"{label} 疑似占位符，请替换为真实值。")


def _is_configured(value: Any) -> bool:
    """判断配置项是否已填写。"""
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    return str(value).strip() != ""


def _is_placeholder_value(value: Any) -> bool:
    """判断是否为明显示例/占位符。"""
    text = str(value).strip().lower()
    if text in _PLACEHOLDER_VALUES:
        return True
    if text.startswith("your_") or text.startswith("change_"):
        return True
    if re.fullmatch(r"x+", text):
        return True
    return False


def _mask_secret(value: Any) -> str:
    """敏感字符串脱敏：保留前后少量字符。"""
    text = str(value or "")
    if not text:
        return "<未配置>"
    if len(text) <= 4:
        return "****"
    return f"{text[:2]}****{text[-2:]}"


def _mask_database_url(url: str) -> str:
    """数据库 URL 脱敏：隐藏密码。"""
    if not url:
        return "<未配置>"
    normalized = Settings._normalize_database_url(url)
    parsed = urlparse(normalized)
    if not parsed.username:
        return url
    password = parsed.password or ""
    masked_password = _mask_secret(password) if password else ""
    host_part = parsed.hostname or ""
    if parsed.port:
        host_part = f"{host_part}:{parsed.port}"
    user_part = parsed.username
    if masked_password:
        user_part = f"{user_part}:{masked_password}"
    path = parsed.path or ""
    return f"mysql+pymysql://{user_part}@{host_part}{path}"
