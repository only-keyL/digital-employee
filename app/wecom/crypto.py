"""WeCom message crypto helpers (Phase 11: reservation only, not production-ready).

Full AES-CBC decrypt for EncodingAESKey is not implemented in this phase.
See docs/企业微信接入指南.md before enabling encrypted callbacks in production.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def decrypt_echostr(*, encoding_aes_key: str, echostr: str) -> str | None:
    """解密 URL 验证 echostr 的预留钩子；当前阶段未实现 AES，返回 None。"""
    if not encoding_aes_key or not echostr:
        return None
    logger.warning(
        "WeCom AES echostr decrypt is not fully implemented in Phase 11; "
        "returning raw echostr when verify signature passes."
    )
    return None


def decrypt_message_body(*, encoding_aes_key: str, body: str) -> str | None:
    """解密加密 POST 回调报文的预留钩子；当前阶段未实现 AES。"""
    if not encoding_aes_key or not body:
        return None
    logger.warning("WeCom AES message decrypt is not fully implemented in Phase 11.")
    return None
