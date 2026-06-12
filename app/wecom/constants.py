"""WeCom integration constants."""

SOURCE_TYPE_WECOM = "wecom"  # 问答来源标识
DEFAULT_GROUP_ID = "wecom_default"  # 默认群聊 ID

MSG_TYPE_TEXT = "text"  # 支持的文本消息类型

UNSUPPORTED_MSG_REPLY = "当前仅支持文本消息，请发送文字问题。"  # 非文本消息回复
EMPTY_CONTENT_REPLY = "请输入有效问题。"  # 空内容回复

NEED_HUMAN_SUFFIX = "建议联系人工处理。"  # 需人工介入时追加后缀

MAX_XML_CONTENT_LENGTH = 2048  # 回复 XML 内容最大长度

DEDUP_MAX_ENTRIES = 10_000  # 去重缓存最大条目数
