"""WeCom callback orchestration — reuses AskService / LangGraph."""

from __future__ import annotations

import logging
import time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.schemas.ask_schema import AskRequest
from app.services.ask_service import AskService
from app.wecom.constants import (
    DEFAULT_GROUP_ID,
    EMPTY_CONTENT_REPLY,
    MSG_TYPE_TEXT,
    SOURCE_TYPE_WECOM,
    UNSUPPORTED_MSG_REPLY,
)
from app.wecom.crypto import decrypt_echostr, decrypt_message_body
from app.wecom.dedup_store import WecomDedupStore
from app.wecom.message_parser import parse_mock_request, parse_plain_xml
from app.wecom.response_builder import build_fixed_reply, build_text_reply
from app.wecom.schemas import WecomInboundMessage, WecomMockCallbackRequest
from app.wecom.url_verify import verify_signature

logger = logging.getLogger(__name__)

_dedup_store: WecomDedupStore | None = None


def _get_dedup_store(settings: Settings) -> WecomDedupStore:
    global _dedup_store
    if _dedup_store is None:
        _dedup_store = WecomDedupStore(ttl_seconds=settings.wecom_dedup_ttl_seconds)
    return _dedup_store


class WecomCallbackService:
    """企业微信回调编排：验签、解密、去重，复用 AskService 生成回复。"""

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.dedup_store = _get_dedup_store(self.settings)

    def verify_callback_url(
        self,
        *,
        msg_signature: str | None,
        timestamp: str | None,
        nonce: str | None,
        echostr: str | None,
    ) -> str:
        """处理 GET 回调 URL 验证，返回解密后的 echostr 明文。"""
        if not echostr:
            raise HTTPException(status_code=400, detail="missing echostr")

        if not self.settings.wecom_enabled:
            return echostr

        token = self.settings.wecom_token
        if not token:
            raise HTTPException(status_code=403, detail="wecom token not configured")

        signature = msg_signature or ""
        ts = timestamp or ""
        nc = nonce or ""
        if not verify_signature(
            token=token,
            timestamp=ts,
            nonce=nc,
            msg_signature=signature,
            echostr=echostr,
        ):
            raise HTTPException(status_code=403, detail="invalid signature")

        if self.settings.wecom_encoding_aes_key:
            decrypted = decrypt_echostr(
                encoding_aes_key=self.settings.wecom_encoding_aes_key,
                echostr=echostr,
            )
            if decrypted:
                return decrypted

        return echostr

    def handle_mock_callback(self, payload: WecomMockCallbackRequest) -> str:
        """处理本地 Mock JSON 回调，返回被动回复 XML。"""
        if not self.settings.wecom_mock_enabled:
            raise HTTPException(status_code=503, detail="wecom mock disabled")

        message = parse_mock_request(payload)
        return self._handle_inbound_message(message)

    def handle_real_callback(
        self,
        body: str,
        *,
        msg_signature: str | None = None,
        timestamp: str | None = None,
        nonce: str | None = None,
    ) -> str:
        """处理真实企业微信 POST XML 回调，验签解密后生成回复。"""
        if not self.settings.wecom_enabled:
            raise HTTPException(status_code=503, detail="wecom disabled")

        raw_body = (body or "").strip()
        if not raw_body:
            raise HTTPException(status_code=400, detail="empty body")

        if self.settings.wecom_encoding_aes_key and "<Encrypt>" in raw_body:
            decrypted = decrypt_message_body(
                encoding_aes_key=self.settings.wecom_encoding_aes_key,
                body=raw_body,
            )
            if decrypted:
                raw_body = decrypted
            else:
                logger.warning("Encrypted WeCom callback received but AES decrypt is not available.")
                placeholder = WecomInboundMessage(
                    msg_id=f"unsupported-{int(time.time())}",
                    from_user="wecom_user",
                    to_user="corp_agent",
                    chat_id=DEFAULT_GROUP_ID,
                    msg_type="encrypt",
                    content="",
                )
                return build_fixed_reply(placeholder, UNSUPPORTED_MSG_REPLY)

        if self.settings.wecom_token and msg_signature and timestamp and nonce:
            if not verify_signature(
                token=self.settings.wecom_token,
                timestamp=timestamp,
                nonce=nonce,
                msg_signature=msg_signature,
                echostr="",
            ):
                logger.warning("WeCom POST signature verification failed.")
                raise HTTPException(status_code=403, detail="invalid signature")

        message = parse_plain_xml(raw_body)
        if message is None:
            placeholder = WecomInboundMessage(
                msg_id=f"parse-fail-{int(time.time())}",
                from_user="wecom_user",
                to_user="corp_agent",
                chat_id=DEFAULT_GROUP_ID,
                msg_type="unknown",
                content="",
            )
            return build_fixed_reply(placeholder, UNSUPPORTED_MSG_REPLY)

        return self._handle_inbound_message(message)

    def _handle_inbound_message(self, message: WecomInboundMessage) -> str:
        cached = self.dedup_store.get_cached_xml(message.msg_id)
        if cached is not None:
            return cached

        if message.msg_type != MSG_TYPE_TEXT:
            xml_body = build_fixed_reply(message, UNSUPPORTED_MSG_REPLY)
            self.dedup_store.save_xml(message.msg_id, xml_body)
            return xml_body

        if not message.content:
            xml_body = build_fixed_reply(message, EMPTY_CONTENT_REPLY)
            self.dedup_store.save_xml(message.msg_id, xml_body)
            return xml_body

        ask_response = AskService(self.session).ask(
            AskRequest(
                question=message.content,
                user_id=message.from_user,
                group_id=message.chat_id or DEFAULT_GROUP_ID,
                source_type=SOURCE_TYPE_WECOM,
            )
        )
        xml_body = build_text_reply(message, ask_response)
        self.dedup_store.save_xml(message.msg_id, xml_body)
        return xml_body
