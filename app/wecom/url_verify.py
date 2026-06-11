"""WeCom URL verification (GET callback)."""

from __future__ import annotations

import hashlib


def compute_signature(*, token: str, timestamp: str, nonce: str, encrypt: str = "") -> str:
    parts = [token, timestamp, nonce]
    if encrypt:
        parts.append(encrypt)
    parts.sort()
    raw = "".join(parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def verify_signature(
    *,
    token: str,
    timestamp: str,
    nonce: str,
    msg_signature: str,
    echostr: str = "",
) -> bool:
    if not token or not timestamp or not nonce or not msg_signature:
        return False
    expected = compute_signature(token=token, timestamp=timestamp, nonce=nonce, encrypt=echostr)
    return expected == msg_signature
