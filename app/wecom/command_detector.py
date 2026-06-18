"""企微指令识别：沉淀 / 模板 / 取消 / 普通问题 / 知识卡片提交。"""

from __future__ import annotations

import re
from enum import Enum


class CommandType(str, Enum):
    DEPOSIT_START = "deposit_start"
    TEMPLATE = "template"
    DEPOSIT_CANCEL = "deposit_cancel"
    KNOWLEDGE_SUBMIT = "knowledge_submit"
    NORMAL_QUESTION = "normal_question"


# 精确匹配的指令集合（去除首尾空格后全等匹配）
_DEPOSIT_START_COMMANDS = frozenset({"【沉淀】", "沉淀", "/deposit"})
_TEMPLATE_COMMANDS = frozenset({"【模板】", "模板", "/template"})
_DEPOSIT_CANCEL_COMMANDS = frozenset({"【取消沉淀】", "取消沉淀", "/cancel"})

# 知识卡片提交特征：至少包含若干字段标签
_KNOWLEDGE_FIELD_PATTERN = re.compile(r"^(标题|问题|答案)[：:]", re.MULTILINE)


class CommandDetector:
    """识别用户消息属于哪类指令或业务动作。"""

    def detect(self, content: str, *, deposit_session_active: bool) -> CommandType:
        text = (content or "").strip()
        if not text:
            return CommandType.NORMAL_QUESTION

        if text in _DEPOSIT_START_COMMANDS:
            return CommandType.DEPOSIT_START
        if text in _TEMPLATE_COMMANDS:
            return CommandType.TEMPLATE
        if text in _DEPOSIT_CANCEL_COMMANDS:
            return CommandType.DEPOSIT_CANCEL

        # 沉淀 session 存在时，非指令文本视为知识卡片提交
        if deposit_session_active:
            if text.startswith("{") or _KNOWLEDGE_FIELD_PATTERN.search(text):
                return CommandType.KNOWLEDGE_SUBMIT
            # 沉淀模式下任意非指令长文本也尝试解析为投稿
            if len(text) >= 20:
                return CommandType.KNOWLEDGE_SUBMIT

        return CommandType.NORMAL_QUESTION
