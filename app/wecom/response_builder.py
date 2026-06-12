"""Build WeCom passive text reply XML."""

from __future__ import annotations

import time

from app.schemas.ask_schema import AskResponse
from app.wecom.constants import MAX_XML_CONTENT_LENGTH, NEED_HUMAN_SUFFIX
from app.wecom.schemas import WecomInboundMessage


def _escape_cdata_content(text: str) -> str:
    """Prevent CDATA terminator injection."""
    return text.replace("]]>", "]]]]><![CDATA[>")


def _truncate_content(text: str, *, max_length: int = MAX_XML_CONTENT_LENGTH) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def build_fixed_reply(message: WecomInboundMessage, content: str) -> str:
    """构建固定文本内容的被动回复 XML。"""
    safe_content = _truncate_content(_escape_cdata_content(content))
    create_time = message.create_time or int(time.time())
    return (
        "<xml>"
        f"<ToUserName><![CDATA[{message.from_user}]]></ToUserName>"
        f"<FromUserName><![CDATA[{message.to_user}]]></FromUserName>"
        f"<CreateTime>{create_time}</CreateTime>"
        "<MsgType><![CDATA[text]]></MsgType>"
        f"<Content><![CDATA[{safe_content}]]></Content>"
        "</xml>"
    )


def build_text_reply(message: WecomInboundMessage, ask_response: AskResponse) -> str:
    """将 AskResponse 转为企业微信被动文本回复 XML。"""
    content = (ask_response.answer or "").strip()
    if not content and ask_response.fallback_reason:
        content = ask_response.fallback_reason
    if ask_response.need_human:
        suffix = NEED_HUMAN_SUFFIX
        if suffix not in content:
            content = f"{content}\n{suffix}" if content else suffix
    return build_fixed_reply(message, content)
