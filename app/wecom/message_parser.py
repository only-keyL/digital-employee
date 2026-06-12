"""Parse WeCom mock JSON and plain XML inbound messages."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from app.wecom.constants import DEFAULT_GROUP_ID
from app.wecom.schemas import WecomInboundMessage, WecomMockCallbackRequest


def _text_or_empty(element: ET.Element | None) -> str:
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def parse_mock_request(payload: WecomMockCallbackRequest) -> WecomInboundMessage:
    """将 Mock JSON 请求转为统一入站消息结构。"""
    return WecomInboundMessage(
        msg_id=payload.msg_id,
        from_user=payload.from_user or "wecom_user_demo",
        to_user=payload.to_user or "corp_agent",
        chat_id=payload.chat_id or DEFAULT_GROUP_ID,
        msg_type=(payload.msg_type or "text").lower(),
        content=(payload.content or "").strip(),
        create_time=payload.create_time,
    )


def parse_plain_xml(body: str) -> WecomInboundMessage | None:
    """解析明文 XML 回调体为入站消息，解析失败返回 None。"""
    text = (body or "").strip()
    if not text:
        return None
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None

    msg_id = _text_or_empty(root.find("MsgId")) or _text_or_empty(root.find("msgid"))
    if not msg_id:
        msg_id = f"xml-{hash(text) & 0xFFFFFFFF:08x}"

    from_user = _text_or_empty(root.find("FromUserName"))
    to_user = _text_or_empty(root.find("ToUserName"))
    msg_type = (_text_or_empty(root.find("MsgType")) or "text").lower()
    content = _text_or_empty(root.find("Content"))
    create_time_raw = _text_or_empty(root.find("CreateTime"))
    create_time = int(create_time_raw) if create_time_raw.isdigit() else None
    chat_id = _text_or_empty(root.find("ChatId")) or from_user or DEFAULT_GROUP_ID

    return WecomInboundMessage(
        msg_id=msg_id,
        from_user=from_user or "wecom_user",
        to_user=to_user or "corp_agent",
        chat_id=chat_id,
        msg_type=msg_type,
        content=content,
        create_time=create_time,
    )
