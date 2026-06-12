"""WeCom URL verification (GET callback)."""

from __future__ import annotations

import hashlib


def compute_signature(*, token: str, timestamp: str, nonce: str, encrypt: str = "") -> str:
    """按企业微信规则计算 SHA1 签名。"""
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
    """校验回调请求签名是否与 msg_signature 一致。"""
    if not token or not timestamp or not nonce or not msg_signature:
        return False
    expected = compute_signature(token=token, timestamp=timestamp, nonce=nonce, encrypt=echostr)
    return expected == msg_signature
