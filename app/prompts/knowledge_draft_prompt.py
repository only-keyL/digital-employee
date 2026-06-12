"""未命中问题由知识卡片草稿生成的 Prompt 模板。"""

KNOWLEDGE_DRAFT_PROMPT_TEMPLATE = """你是企业实施知识库编辑助手。请根据以下未命中问题，生成一条知识卡片草稿。

未命中问题：{{question}}
问题摘要：{{summary}}
出现频次：{{frequency}}
所属系统（如有）：{{system_name}}
所属模块（如有）：{{module_name}}
标签（如有）：{{tags}}

请严格按以下 JSON 格式输出，不要输出其他内容：
{
  "title": "知识卡片标题，不超过50字",
  "question": "标准问题表述",
  "answer": "标准答案，简明可执行",
  "troubleshooting_steps": "排查步骤",
  "solution": "处理建议",
  "risk_notice": "风险提醒，不得编造高风险操作",
  "system_name": "所属系统",
  "module_name": "所属模块",
  "tags": "标签，逗号分隔"
}

要求：
1. 基于问题合理推断，不确定的内容写“待人工补充”
2. 不得编造需要管理员密码、直接改生产库等高风险操作
3. answer 必须非空
"""
