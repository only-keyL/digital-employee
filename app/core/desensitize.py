"""基础脱敏工具：用于日志、健康检查接口与 LangSmith trace 输出。"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse, urlunparse

# 疑似 API Key / Token 模式（sk-、Bearer 等）
_TOKEN_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]+\b", re.IGNORECASE),
    re.compile(r"\b[A-Za-z0-9]{20,}\b"),
)
_PHONE_PATTERN = re.compile(r"\b1[3-9]\d{9}\b")
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def mask_secret(value: str | None) -> str:
    """对 API Key、Token、密码等敏感字符串脱敏，保留前 4 位与后 4 位。"""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "***"
    return f"{text[:4]}***{text[-4:]}"


def mask_url(value: str | None) -> str:
    """对 URL 脱敏，隐藏用户名与密码（如 Redis URL）。"""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        parsed = urlparse(text)
        if not parsed.scheme:
            return mask_secret(text)
        username = parsed.username or ""
        password = parsed.password or ""
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        netloc = host
        if username:
            masked_user = mask_secret(username) if len(username) > 4 else "***"
            if password:
                netloc = f"{masked_user}:***@{host}"
            else:
                netloc = f"{masked_user}@{host}"
        return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
    except Exception:
        return "***"


def sanitize_text(value: str | None, max_length: int = 200) -> str:
    """对文本做基础脱敏并截断，避免上传完整内部问题/答案/知识正文。"""
    if value is None:
        return ""
    text = str(value)
    if not text:
        return ""
    text = _PHONE_PATTERN.sub("[手机号已隐藏]", text)
    text = _EMAIL_PATTERN.sub("[邮箱已隐藏]", text)
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub("[敏感信息已隐藏]", text)
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text


def sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    """递归脱敏字典中的字符串值，供接口与日志安全输出。"""
    sensitive_keys = frozenset(
        {
            "password",
            "secret",
            "token",
            "api_key",
            "apikey",
            "authorization",
            "redis_url",
            "qdrant_api_key",
            "llm_api_key",
            "langsmith_api_key",
            "wecom_secret",
            "wecom_token",
            "wecom_encoding_aes_key",
            "database_url",
        }
    )
    result: dict[str, Any] = {}
    for key, value in data.items():
        lower_key = key.lower()
        if isinstance(value, dict):
            result[key] = sanitize_dict(value)
        elif isinstance(value, list):
            result[key] = [
                sanitize_dict(item) if isinstance(item, dict) else sanitize_text(str(item))
                if isinstance(item, str)
                else item
                for item in value
            ]
        elif isinstance(value, str):
            if any(s in lower_key for s in sensitive_keys):
                if "url" in lower_key:
                    result[key] = mask_url(value)
                else:
                    result[key] = mask_secret(value)
            else:
                result[key] = sanitize_text(value)
        else:
            result[key] = value
    return result
