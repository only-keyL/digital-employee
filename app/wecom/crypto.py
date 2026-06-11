"""WeCom message crypto helpers (Phase 11: reservation only, not production-ready).

Full AES-CBC decrypt for EncodingAESKey is not implemented in this phase.
See docs/WECOM_INTEGRATION.md before enabling encrypted callbacks in production.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def decrypt_echostr(*, encoding_aes_key: str, echostr: str) -> str | None:
    """Reserved hook for decrypting URL verification echostr.

    Returns None when AES decrypt is unavailable (current default).
    """
    if not encoding_aes_key or not echostr:
        return None
    logger.warning(
        "WeCom AES echostr decrypt is not fully implemented in Phase 11; "
        "returning raw echostr when verify signature passes."
    )
    return None


def decrypt_message_body(*, encoding_aes_key: str, body: str) -> str | None:
    """Reserved hook for decrypting encrypted POST callback bodies."""
    if not encoding_aes_key or not body:
        return None
    logger.warning("WeCom AES message decrypt is not fully implemented in Phase 11.")
    return None
