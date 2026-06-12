# 项目学习复盘：digital-employee-assistant

> 本文档基于当前代码只读整理，帮助开发者理解 MVP 的业务链路、技术架构、RAG、LangGraph 与 LangSmith。  
> **定位**：可演示、可验收的 Demo / MVP，不是生产上线版本。

---

## 1. 项目一句话定位

**面向企业微信实施群的知识沉淀型数字员工 Demo**：把「提问 → 向量检索 → LLM 回答 → 日志/反馈/统计 → 未命中沉淀为知识卡片」串成闭环；Web `/ask-test` 与企微 Mock 回调共用同一套 `AskService` + LangGraph 问答链路。

---

## 2. 当前 MVP 已完成的能力

| 领域 | 能力 | 主要入口 / 代码 |
|------|------|-----------------|
| 知识管理 | CRUD、审核、启停、逻辑删除 | `app/routers/knowledge_router.py`、`app/services/knowledge_service.py` |
| 向量同步 | approved+enabled 卡片写入 Qdrant | `app/services/vector_sync_service.py` → `VectorSyncService.sync_card` |
| 智能问答 | RAG + LangGraph + LLM | `POST /api/ask` → `AskService.ask` |
| 在线测试 | Web 提问页 | `app/routers/page_router.py` → `ask_test_page` |
| 未命中沉淀 | pending → converted/ignored | `app/services/unanswered_convert_service.py` |
| 反馈统计 | useful/useless/need_human | `app/services/feedback_service.py`、`app/services/statistics_service.py` |
| LangSmith | 可选 tracing，trace_id 落库 | `app/observability/trace_service.py` → `TraceService` |
| 企微 | Mock JSON 回调 + 真实接口预留 | `app/services/wecom_callback_service.py` |

阶段一至十一全部完成，详见 `docs/MVP交付说明.md`。

---

## 3. 用户提问到返回答案的完整调用链

### 3.1 Web 路径（`/ask-test` → `/api/ask`）

```text
浏览器 /ask-test
  → app/static/js/ask_test.js（fetch POST /api/ask）
  → app/routers/ask_router.py :: ask_question
  → app/services/ask_service.py :: AskService.ask
  → app/agent/graph_runner.py :: AskGraphRunner.run
  → app/agent/workflow.py :: get_compiled_ask_graph().invoke
  → [8 个 LangGraph 节点，见第 5 节]
  → AskService._map_state_to_response
  → JSON AskResponse 返回前端
```

### 3.2 企业微信 Mock 路径

```text
POST /api/wecom/mock/callback（JSON）
  → app/routers/wecom_router.py :: wecom_mock_callback
  → app/services/wecom_callback_service.py :: WecomCallbackService.handle_mock_callback
  → parse_mock_request（app/wecom/message_parser.py）
  → WecomCallbackService._handle_inbound_message
       ├─ WecomDedupStore.get_cached_xml（重复 msg_id 直接返回缓存 XML）
       └─ AskService.ask（source_type=wecom）
  → app/wecom/response_builder.py :: build_text_reply
  → application/xml 文本回复（非 AskResponse JSON）
```

企微与 Web **共用** `AskService.ask` → LangGraph，差异仅在入口与响应格式（`app/services/wecom_callback_service.py` 第 167–177 行）。

### 3.3 LangSmith 可选分支（不改变问答结果）

```text
AskGraphRunner.run
  → TraceService.is_enabled()（app/config/settings.py :: is_langsmith_enabled）
  → 若开启：TraceService.invoke_graph（包装 graph.invoke + LangChainTracer）
  → graph 完成后：TraceService.persist_trace_id → QuestionRepository.update_langsmith_trace_id
  → 若失败：降级为普通 graph.invoke（app/observability/trace_service.py :: invoke_graph）
```

---

## 4. `/api/ask` 代码调用链（文件 + 函数）

### 4.1 HTTP 层

| 步骤 | 文件 | 函数 |
|------|------|------|
| 路由注册 | `app/main.py` | `create_app` → `include_router(ask_router)` |
| 接收请求 | `app/routers/ask_router.py` | `ask_question` |
| 请求体 | `app/schemas/ask_schema.py` | `AskRequest` |
| 响应体 | `app/schemas/ask_schema.py` | `AskResponse` |
| DB Session | `app/db/database.py` | `get_db`（Depends 注入） |

`ask_question` 异常时直接构造 `AskResponse` 降级（SQLAlchemyError / 通用 Exception），不抛 500（`app/routers/ask_router.py` 第 18–38 行）。

### 4.2 服务层

| 步骤 | 文件 | 函数 |
|------|------|------|
| 入口 | `app/services/ask_service.py` | `AskService.ask` |
| 构造初始状态 | `app/services/ask_service.py` | `AskService._build_initial_state` |
| 执行图 | `app/agent/graph_runner.py` | `AskGraphRunner.run` |
| 映射响应 | `app/services/ask_service.py` | `AskService._map_state_to_response` |

### 4.3 编排层

| 步骤 | 文件 | 函数 |
|------|------|------|
| 获取编译图 | `app/agent/workflow.py` | `get_compiled_ask_graph`（`@lru_cache` 进程内单例） |
| 构建图 | `app/agent/workflow.py` | `build_ask_workflow` |
| 条件路由 | `app/agent/workflow.py` | `route_after_validate` / `route_after_retrieve` / `route_after_match` |
| 执行 | LangGraph | `graph.invoke(state, config)`，`config={"configurable": {"db": session}}` |

### 4.4 节点层（详见第 5 节）

所有节点在 `app/agent/nodes.py`，通过 `_get_db_session(config)` 读取 `configurable["db"]`。

### 4.5 落库层

| 步骤 | 文件 | 函数 |
|------|------|------|
| 写日志 | `app/agent/nodes.py` | `write_log_node` |
| 日志服务 | `app/services/ask_log_service.py` | `AskLogService.write_log` |
| 写 question_log | `app/services/ask_log_service.py` | `AskLogService.create_question_log` |
| 写未命中 | `app/services/ask_log_service.py` | `AskLogService.upsert_unanswered_question` |
| 提交 | `app/repositories/question_repository.py` | `QuestionRepository.save` |

---

## 5. LangGraph 工作流节点说明

定义文件：`app/agent/workflow.py` → `build_ask_workflow`  
节点实现：`app/agent/nodes.py`  
路由常量：`app/agent/constants.py`

```text
START
  → validate_input          （校验空问题）
  → [空] END                route_after_validate → ROUTE_END
  → preprocess_question     （脱敏/改写占位：目前 question_masked = question_raw）
  → retrieve                （RetrievalService.retrieve）
  → [检索异常] error_fallback
  → match_judge             （根据 _raw_matched 写 matched/sources）
  → [命中] generate_answer  （AnswerGenerationService.generate）
  → [未命中] handle_miss    （固定 FALLBACK_ANSWER，不调 LLM）
  → write_log               （AskLogService.write_log）
  → END
```

| 节点 | 函数 | 职责 |
|------|------|------|
| `validate_input` | `validate_input_node` | 空问题 → `is_valid=False`，`should_write_log=False`，直接 END |
| `preprocess_question` | `preprocess_question_node` | 填充 `question_masked`、`rewritten_question`、`source_type` 等 |
| `retrieve` | `retrieve_node` | 调用 `RetrievalService.retrieve`，写 `_raw_*` 与 `retrieval_hits` |
| `match_judge` | `match_judge_node` | 将检索结果转为 `matched`、`sources`、`similarity_score` |
| `generate_answer` | `generate_answer_node` | `_hits_from_state` + `AnswerGenerationService.generate` |
| `handle_miss` | `handle_miss_node` | 未命中固定文案 `FALLBACK_ANSWER`（`app/agent/constants.py`） |
| `error_fallback` | `error_fallback_node` | 检索异常固定文案 `RETRIEVAL_ERROR_ANSWER` |
| `write_log` | `write_log_node` | `AskLogService.write_log`，写 `question_log_id`、`latency_ms` |

**设计原则**（`docs/架构决策.md` §13）：LangGraph **只编排**，检索/生成逻辑在 Service，节点内不直接写 SQL 业务规则以外的逻辑。

---

## 6. AskState 字段说明

定义：`app/agent/ask_state.py` → `AskState`（TypedDict）

| 分组 | 字段 | 含义 | 主要写入节点 |
|------|------|------|--------------|
| 输入 | `question_raw` | 原始问题 | `AskService._build_initial_state` / `validate_input_node` |
| | `question_masked` | 脱敏后问题（当前=原文） | `preprocess_question_node` |
| | `rewritten_question` | 改写问题（当前=原文） | `preprocess_question_node` |
| | `user_id` / `group_id` / `source_type` | 用户与来源（web/wecom） | 初始 state / `preprocess_question_node` |
| 流程 | `is_valid` | 是否有效问题 | `validate_input_node` |
| | `should_write_log` | 是否写 question_log | `validate_input_node` |
| | `retrieval_error` | Qdrant/检索是否异常 | `retrieve_node` |
| | `route` | 内部路由标记 | 各节点 |
| 检索 | `matched` | 是否命中知识库 | `match_judge_node` |
| | `similarity_score` | 最高相似度 | `match_judge_node` |
| | `sources` | 返回前端的来源列表 | `match_judge_node` |
| | `matched_card_ids` | 逗号分隔 card_id | `match_judge_node` |
| | `retrieval_hits` | 检索 hit 字典列表 | `retrieve_node` |
| | `_raw_matched` 等 | 检索原始结果 | `retrieve_node` |
| 生成 | `answer` | 最终回答文本 | `generate_answer_node` / `handle_miss_node` / `error_fallback_node` |
| | `need_human` / `risk_level` | 是否需人工 / 风险 | `generate_answer_node` 等 |
| | `llm_tokens` / `answer_time_ms` | LLM 消耗与耗时 | `generate_answer_node` |
| | `error_stage` / `error_message` | LLM 降级信息 | `generate_answer_node` |
| 计时 | `started_at` / `retrieval_time_ms` / `latency_ms` | 性能指标 | 各节点 |
| 输出 | `question_log_id` | 提问日志 ID | `write_log_node` |
| | `fallback_reason` | 未命中/异常原因 | 多节点 |
| | `intent` | 意图（固定 question） | 初始 state |

LangSmith **不会**把完整 AskState 明文上报，仅安全 metadata（`app/observability/redaction.py` → `build_safe_metadata`）。

---

## 7. RAG 链路说明

### 7.1 数据流总览

```text
MySQL knowledge_card（主数据）
  → build_knowledge_content_text（app/services/knowledge_content.py）
  → EmbeddingService.embed_text（app/rag/embedding_service.py）
  → QdrantStore.upsert_knowledge_card（app/rag/qdrant_store.py）
  → 向量存于 ./storage/qdrant（local）

用户问题
  → EmbeddingService.embed_text（同一模型）
  → QdrantStore.search（top_k，默认 5）
  → RetrievalService._validate_hits（回查 MySQL 确认 approved+enabled）
  → 阈值判断 similarity_threshold（默认 0.75）
  → 命中则 AnswerGenerationService 拼 context 调 LLM
```

### 7.2 MySQL

| 职责 | 代码 |
|------|------|
| 知识卡片主数据 | `app/models/knowledge_card.py` |
| 可检索条件 | `KnowledgeRepository.get_searchable_by_id`（`app/repositories/knowledge_repository.py`） |
| 是否应入向量库 | `should_index_card`（`app/services/vector_sync_service.py`）：`deleted=0` 且 `audit_status=approved` 且 `enabled=1` |
| 同步向量 | `VectorSyncService.sync_card` → `QdrantStore.upsert_knowledge_card` / `delete_knowledge_card` |

**要点**：Qdrant 只做检索索引，**不替代** MySQL；检索后仍回 MySQL 校验卡片状态（`RetrievalService._validate_hits`）。

### 7.3 Embedding

| 项 | 代码 |
|----|------|
| 工厂 | `get_embedding_service`（`app/rag/embedding_service.py`，`@lru_cache`） |
| 默认 Provider | `FastEmbedProvider`（`BAAI/bge-small-zh-v1.5`，512 维） |
| 配置 | `settings.embedding_provider`、`settings.embedding_model`（`app/config/settings.py`） |
| Mock | `MockEmbeddingProvider`（测试/无模型时用） |

### 7.4 Qdrant

| 项 | 代码 |
|----|------|
| 客户端 | `QdrantStore._create_client` → `QdrantClient(path=settings.qdrant_local_path)` |
| Collection | `settings.qdrant_collection`（默认 `knowledge_cards`） |
| 距离 | COSINE（`settings.qdrant_distance`） |
| 检索 | `QdrantStore.search` → `query_points` |
| 重建 | `scripts/rebuild_qdrant.py` → `VectorSyncService` / `QdrantStore.rebuild_from_mysql` |

**限制**：local 模式 + 单实例 uvicorn；多进程同时访问会锁库（见 `docs/本地启动说明.md`）。

### 7.5 RetrievalService

文件：`app/services/retrieval_service.py`

| 方法 | 行为 |
|------|------|
| `retrieve(question)` | `qdrant.search` → `_validate_hits` → 与 `settings.similarity_threshold` 比较 |
| 异常 | 返回 `RetrievalResult.error`，`retrieve_node` 走 `error_fallback` |
| 未命中 | `matched=False`，`fallback_reason` 如「向量检索未命中」「相似度低于阈值」 |
| 返回 sources | 最多 `MAX_SOURCES=3` 条 |

### 7.6 AnswerGenerationService

文件：`app/services/answer_generation_service.py`

| 方法 | 行为 |
|------|------|
| `generate(question, hits)` | `build_context` 拼知识卡片字段 → `PromptService.generate_answer` |
| DeepSeek 模式 | `LLMFactory.use_deepseek_primary()` 为真时，`PromptService.check_quality` 质检 |
| 降级 | `_degrade_from_mock_or_template` / `_degrade_from_template` |
| 来源标记 | `_ensure_source_line` 保证 answer 含「答案来源」 |

**未命中路径不调 LLM**：由 `handle_miss_node` 直接返回 `FALLBACK_ANSWER`（`app/agent/nodes.py`）。

---

## 8. LangChain 在项目中承担的职责

LangChain **不是**单独一条问答链路，而是 **LLM 调用与 tracing 的基础设施**：

| 职责 | 位置 |
|------|------|
| LLM 抽象 | `app/llm/base.py` → `BaseLLMClient` |
| Chat 调用 | `app/llm/deepseek_client.py` → `DeepSeekClient`；`app/llm/mock_llm.py` → `MockLLM` |
| Provider 选择 | `app/llm/llm_factory.py` → `LLMFactory.get_llm_client` / `use_deepseek_primary` |
| Prompt + 调用 | `app/llm/prompt_service.py` → `PromptService.generate_answer` / `check_quality` |
| Prompt 模板 | `app/prompts/answer_prompt.py`、`quality_check_prompt.py`、`knowledge_draft_prompt.py` |
| Tracer | `langchain_core.tracers.langchain.LangChainTracer`（`app/observability/trace_service.py`） |
| RunnableConfig | LangGraph 节点签名 `(state, config: RunnableConfig)`（`app/agent/nodes.py`） |

**未使用 LangChain 的部分**：向量检索由自研 `RetrievalService` + `QdrantStore` 完成，非 LangChain Retriever 链。

---

## 9. LangGraph 在项目中承担的职责

| 职责 | 说明 | 代码 |
|------|------|------|
| 流程编排 | 8 节点 + 条件边 | `app/agent/workflow.py` |
| 状态机 | 统一 `AskState` 在各节点间 merge | `StateGraph(AskState)` |
| Session 注入 | 每请求 `configurable["db"]`，不缓存 Session | `AskGraphRunner.run`、`_get_db_session` |
| 图编译缓存 | 进程内单例 compiled graph | `get_compiled_ask_graph`（`@lru_cache`） |
| 分支逻辑 | 空问题 / 检索异常 / 命中 / 未命中 | `route_after_*` 函数 |

**LangGraph 不负责**：写业务 SQL、直接调 Qdrant、决定 `/api/ask` JSON 结构（由 `AskService._map_state_to_response` 负责）。

---

## 10. LangSmith 在项目中承担的职责

| 职责 | 代码 |
|------|------|
| 开关 | `settings.is_langsmith_enabled` = `langsmith_tracing and langsmith_api_key`（`app/config/settings.py`） |
| 入口 | `AskGraphRunner.run` → `TraceService.invoke_graph` |
| Tracing | `LangChainTracer` + `langsmith.Client`（`hide_inputs` / `hide_outputs`） |
| 环境变量兼容 | `TraceService._langchain_compat_env` 临时设置 `LANGCHAIN_*` |
| 安全 metadata | `app/observability/redaction.py` → `build_safe_metadata`（不含问题/答案全文） |
| trace_id 落库 | `TraceService.persist_trace_id` → `QuestionRepository.update_langsmith_trace_id` |
| 降级 | tracing 失败 → 普通 `graph.invoke`，不影响 `AskResponse`（`TraceService.invoke_graph`） |

**默认关闭**；`trace_id` **不返回前端**，只写入 `question_log.langsmith_trace_id`。

---

## 11. 未命中问题如何沉淀为知识卡片

### 11.1 自动记录（问答链路内）

```text
write_log_node
  → AskLogService.write_log（app/services/ask_log_service.py）
  → 若 matched=False 且 retrieval_error=False
  → upsert_unanswered_question
       ├─ 已有 pending 同 normalized_question → increment_frequency
       └─ 否则新建 UnansweredQuestion(status=pending)
```

关键函数：`AskLogService.upsert_unanswered_question`、`UnansweredRepository.get_pending_by_normalized` / `increment_frequency`。

**不写未命中**：空问题（`should_write_log=False`）、检索异常（`retrieval_error=True`）。

### 11.2 人工闭环（管理页 / API）

| 步骤 | 操作 | 代码 |
|------|------|------|
| 1 | 列表查看 pending | `app/services/unanswered_service.py`、`app/routers/unanswered_router.py` |
| 2 | AI 草稿预览（不落库） | `app/services/unanswered_draft_service.py` → `PromptService.generate_knowledge_draft` |
| 3 | convert 转 draft 卡片 | `UnansweredConvertService.convert_to_draft` → `KnowledgeService.create_draft_without_commit` |
| 4 | 标记 converted | `UnansweredRepository.mark_converted` |
| 5 | ignore | `UnansweredConvertService.ignore` |
| 6 | 人工审核 approved | `KnowledgeService` 审核流程 |
| 7 | 同步 Qdrant | `VectorSyncService.sync_card`（仅 approved+enabled） |

**规则**（`docs/架构决策.md` §14）：convert 创建 `audit_status=draft`，**不**自动同步向量；审核通过后才进入 RAG 索引。

---

## 12. 当前项目有哪些不足

| 类别 | 不足 | 依据 |
|------|------|------|
| 部署 | Qdrant local 单实例，无集群/高可用 | `QdrantStore._create_client` |
| 安全 | 无完整脱敏、无 API 鉴权 | `preprocess_question_node` 仅复制原文 |
| 企微 | AES 加解密未完整、Mock 为主 | `app/wecom/crypto.py` |
| 去重 | 企微 msg_id 进程内 TTL，重启丢失 | `app/wecom/dedup_store.py` |
| LLM | 默认 Mock，DeepSeek 质检增加延迟 | `LLMFactory`、`AnswerGenerationService` |
| 观测 | LangSmith 默认关，无告警平台 | `TraceService.is_enabled` |
| 产品 | 单轮问答，无多轮/流式 | 架构设计 |
| 测试 | 以脚本验收为主，单元测试少 | `scripts/check_*.py` |

---

## 13. 后续为了面试和学习，最应该增强的 5 个点

1. **完整 RAG 评测体系**  
   在现有 `RetrievalService` 上增加 hit@k、MRR 评测脚本与 golden dataset，能说清 threshold 如何调优。  
   相关代码：`app/services/retrieval_service.py`、`scripts/check_rag.py`。

2. **LangGraph 可视化与节点级单测**  
   为 `build_ask_workflow` 画状态图，对每个 `route_after_*` 和节点写 pytest，面试可讲清分支覆盖。  
   相关代码：`app/agent/workflow.py`、`app/agent/nodes.py`。

3. **DeepSeek 真实链路 + 降级策略文档化**  
   跑通 `LLM_PROVIDER=deepseek`，理解 `PromptService.check_quality` 与 `_degrade_from_*` 降级链。  
   相关代码：`app/llm/prompt_service.py`、`app/services/answer_generation_service.py`。

4. **LangSmith 开启并理解 trace 结构**  
   配置 `LANGSMITH_TRACING=true`，对照 `TraceService` 与 `build_safe_metadata` 理解 observability 与隐私边界。  
   相关代码：`app/observability/trace_service.py`、`scripts/check_langsmith.py`。

5. **未命中沉淀端到端故事**  
   从 `upsert_unanswered_question` 到 `convert_to_draft` 再到 `VectorSyncService.sync_card`，能口述知识回流如何进入 Qdrant。  
   相关代码：`app/services/ask_log_service.py`、`app/services/unanswered_convert_service.py`、`app/services/vector_sync_service.py`。

---

## 14. 大白话总结：这个项目是怎么工作的

你可以把它想成一个**「实施群 FAQ 机器人 + 知识运营后台」的 Demo**：

1. **知识先放进 MySQL**  
   管理员维护知识卡片，审核通过后，系统把卡片内容变成向量，存进本地 Qdrant（像一本可语义搜索的电子书索引）。

2. **用户提问（Web 或企微 Mock）**  
   问题进来后，不是直接扔给大模型，而是先走 **LangGraph 流水线**：  
   空问题直接打回 → 把问题向量化 → 去 Qdrant 找最像的知识卡片 → 分数够高算「命中」。

3. **命中了就生成回答**  
   把检索到的卡片内容拼成上下文，交给 **MockLLM 或 DeepSeek** 写回答，并附上「答案来源」。  
   没命中就不调 LLM，给用户一段「没找到，已记录待沉淀」的固定话术。

4. **每次都记日志**  
   有效问题写 `question_log`；没命中还会汇总到 `unanswered_question`，同样问题问多了 `frequency` 会增加。

5. **运营人员可以「补知识」**  
   在未命中列表里预览 AI 草稿、一键转成 draft 知识卡片，审核通过后再同步进 Qdrant，下次类似问题就能命中。

6. **用户还能点有用/无用**  
   反馈进统计看板，看命中率和满意度。

7. **企微和 Web 共用同一套大脑**  
   企微 Mock 只是把 JSON 消息转成 `AskRequest(source_type=wecom)`，答案再包成 XML 返回；核心问答逻辑没有两套。

8. **LangSmith 是可选「黑匣子记录仪」**  
   默认关；开了也只记安全 metadata 和 trace 结构，不把完整问题答案上传。

**一句话**：MySQL 管知识、Qdrant 管「像不像」、LangGraph 管「先干啥后干啥」、LLM 管「怎么说人话」、日志和未命中表管「怎么越用越聪明」——但目前仍是 **本地 Demo**，离生产还差部署、安全、企微真接入和运维体系。

---

## 附录：建议阅读顺序

1. `app/routers/ask_router.py` → `app/services/ask_service.py`  
2. `app/agent/workflow.py` → `app/agent/nodes.py`  
3. `app/services/retrieval_service.py` → `app/rag/qdrant_store.py`  
4. `app/services/answer_generation_service.py` → `app/llm/prompt_service.py`  
5. `app/services/ask_log_service.py` → `app/services/unanswered_convert_service.py`  
6. `app/observability/trace_service.py`  
7. `app/services/wecom_callback_service.py`

相关文档：`docs/MVP交付说明.md`、`docs/架构决策.md`、`docs/企业微信接入指南.md`。
