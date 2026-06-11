# 数字员工助手 — 总阶段规划

> 文件驱动协作：GPT 负责规划与验收口径，Cursor 负责按 `STAGE_CONTROL.md` 执行。每阶段完成后更新本文件「当前进度」。

## 项目定位

企业微信实施群知识沉淀型数字员工 Demo。MySQL 为业务主库，分阶段接入向量检索、LLM、工作流与观测能力。企业微信真实接入为增强项，不阻塞 MVP。

## 阶段总览

| 阶段 | 名称 | 状态 |
|------|------|------|
| 阶段一 | 项目骨架 | ✅ 已完成 |
| 阶段二 | MySQL + 基础表结构 + 只读列表页 | ✅ 已完成 |
| 阶段三 | 知识卡片 CRUD + Seed 数据 | ✅ 已完成 |
| 阶段四 | 在线测试页面 + 假问答流程 | ✅ 已完成 |
| 阶段五 | Embedding + Qdrant 接入 | ✅ 已完成 |
| 阶段六 | LangChain + DeepSeek / MockLLM | ✅ 已完成 |
| 阶段七 | LangGraph 工作流接入 | ✅ 已完成 |
| 阶段八 | 未命中沉淀闭环 | ✅ 已完成 |
| 阶段九 | 反馈 + 统计看板 | ✅ 已完成 |
| 阶段十 | LangSmith 观测 | ✅ 已完成 |
| 阶段十一 | 企业微信接口预留 | ✅ 已完成 |

## 各阶段说明

### 阶段一：项目骨架

- FastAPI + Jinja2 基础结构
- 健康检查、布局模板、静态资源
- `scripts/check_health.py`

### 阶段二：MySQL + 基础表结构 + 只读列表页

- 6 张核心表与 ORM Model
- Repository / Service / Router 分层
- 只读列表页与统计框架
- `scripts/check_db.py`

### 阶段三：知识卡片 CRUD + Seed 数据

- 知识卡片新增、编辑、审核、启停、逻辑删除
- 演示数据 seed（5 条 approved + enabled）
- `scripts/check_seed_data.py`

### 阶段四：在线测试页面 + 假问答流程

- `/ask-test` 在线测试页
- `POST /api/ask` 规则匹配模拟命中
- `question_log` / `unanswered_question` 写入
- `scripts/check_full_flow.py`

### 阶段五：Embedding + Qdrant 接入

- Embedding 服务与 Qdrant 本地 collection
- 知识卡片向量同步与重建
- `/api/ask` 规则匹配替换为向量检索
- 仍不接 DeepSeek / LangGraph

### 阶段六：LangChain + DeepSeek / MockLLM

- LLM 答案生成接入
- MockLLM 便于本地无 Key 验收

### 阶段七：LangGraph 工作流接入

- Agent 工作流编排
- 检索、生成、兜底等节点串联

### 阶段八：未命中沉淀闭环

- 未命中问题转知识卡片草稿
- 沉淀审核与回流

### 阶段九：反馈 + 统计看板

- 有用 / 无用 / 需人工反馈提交
- 统计看板增强

### 阶段十：LangSmith 观测

- Trace 与链路观测接入

### 阶段十一：企业微信接口预留

- 企微回调与消息接口预留（增强项）

## 当前进度

**已完成：阶段一至阶段十一（MVP 闭环）。**

**等待用户验收阶段十一；无后续规划阶段。**

## 协作文件索引

| 文件 | 用途 |
|------|------|
| `docs/STAGE_CONTROL.md` | 当前阶段目标、禁止事项、执行模式 |
| `docs/ACCEPTANCE_CHECKLIST.md` | 各阶段验收命令与通过标准 |
| `docs/DECISIONS.md` | 已确定架构决策（勿随意推翻） |
| `docs/CURSOR_EXECUTION_LOG.md` | Cursor 每轮执行记录 |
| `.cursor/rules/project.mdc` | Cursor 项目级行为约束 |
