# MVP 最终交付说明

> **digital-employee-assistant** — 企业微信实施群知识沉淀型数字员工  
> 阶段一至十一已全部完成。本文档为 MVP 交付总览，**不是生产上线手册**。

## 1. 项目定位

面向企业微信实施群的**知识沉淀型数字员工 Demo**。目标是在实施现场将重复答疑、散落经验转化为可检索、可审核、可统计的知识资产，并预留企业微信接入能力。

**当前状态**：可演示、可脚本验收的 **MVP**；业务闭环（问答 → 沉淀 → 反馈 → 统计）已打通。

**不是**：已上线的生产系统；不含高可用部署、完整安全合规、真实企微生产接入。

**无阶段十二**：后续事项仅作为生产化 backlog，不纳入当前开发阶段。

---

## 2. MVP 交付范围

| 维度 | 交付内容 |
|------|----------|
| 知识管理 | 知识卡片 CRUD、审核、启停、逻辑删除、向量同步 |
| 智能问答 | `/api/ask` + `/ask-test`，Qdrant 检索 + LLM 生成 |
| 流程编排 | LangGraph 8 节点（validate → write_log） |
| 未命中沉淀 | pending → converted / ignored，AI 草稿预览 |
| 反馈统计 | useful / useless / need_human，统计看板 |
| 观测 | LangSmith 可选 tracing（默认关闭） |
| 企微 | Mock JSON 回调 + 真实接口预留 |

---

## 3. 阶段一至十一完成能力总表

| 阶段 | 名称 | 状态 | 主验收脚本 |
|------|------|------|------------|
| 一 | 项目骨架 | ✅ | `check_health.py` |
| 二 | MySQL + 基础表 + 列表页 | ✅ | `check_db.py` |
| 三 | 知识卡片 CRUD + Seed | ✅ | `check_seed_data.py` |
| 四 | 在线测试 + 假问答流程 | ✅ | `check_full_flow.py` |
| 五 | Embedding + Qdrant | ✅ | `check_rag.py` |
| 六 | LangChain + DeepSeek / MockLLM | ✅ | `check_llm.py` |
| 七 | LangGraph 工作流 | ✅ | `check_graph.py` |
| 八 | 未命中沉淀闭环 | ✅ | `check_unanswered_flow.py` |
| 九 | 反馈 + 统计看板 | ✅ | `check_feedback_stats.py` |
| 十 | LangSmith 观测 | ✅ | `check_langsmith.py` |
| 十一 | 企业微信接口预留 | ✅ | `check_wecom_mock.py` |

---

## 4. 已完成能力清单

### 知识库

- 知识卡片新增、编辑、审核（draft / pending / approved / rejected）
- 启停、逻辑删除、`vector_status` 同步状态
- Seed 演示数据（5+ 条 approved + enabled）
- 单卡向量同步与全量 `rebuild_qdrant.py`

### 问答

- `POST /api/ask`：向量检索 → LangGraph 编排 → LLM 答案生成
- `/ask-test` 在线测试页
- 命中返回 `sources`、`similarity_score`、`answer`
- 未命中写 `unanswered_question`，`frequency` 递增
- 空问题不写 `question_log`

### 沉淀

- 未命中列表与详情；AI/Mock 草稿预览（不落库）
- convert → 知识卡片 draft；ignore 终态
- draft 审核通过后可同步 Qdrant

### 反馈与统计

- 每条 `question_log_id` 仅可反馈一次
- 满意度：`useful / (useful + useless)`，`need_human` 不计入分母
- 统计看板：命中率、未命中率、Top 未命中、Top 负反馈

### 观测（可选）

- LangSmith tracing，`langsmith_trace_id` 仅落库
- 默认 `LANGSMITH_TRACING=false`

### 企业微信

- `POST /api/wecom/mock/callback` JSON Mock，复用 `AskService`
- `GET/POST /api/wecom/callback` 真实预留
- `source_type=wecom` 落库；`msg_id` 进程内去重

---

## 5. Demo / Mock 能力说明

| 能力 | 类型 | 说明 |
|------|------|------|
| LLM 答案生成 | **Mock（默认）** | `LLM_PROVIDER=mock`，答案含「Mock 模型回答」 |
| DeepSeek | **可选** | 配置 `DEEPSEEK_API_KEY` 后可用，失败降级 Mock |
| Embedding | **Demo** | fastembed 本地模型，首次需下载 |
| Qdrant | **Demo** | `local` 模式，`./storage/qdrant`，**单实例 uvicorn** |
| LangSmith | **Mock/可选** | 默认关闭，无 Key 可运行 |
| 企业微信 | **Mock + 预留** | Mock JSON 为主；`WECOM_ENABLED=false` |
| 企微去重 | **Demo** | 进程内 TTL，重启 uvicorn 后清空 |
| 问题脱敏 | **未实现** | `question_masked` 暂等于原文 |

---

## 6. 尚未生产化能力说明

| 领域 | 缺口 |
|------|------|
| 企微真实接入 | AES 加解密未完整、需公网 HTTPS、无 Redis 多实例去重 |
| 部署 | Qdrant 非集群；无 MQ/Redis；单进程 Qdrant 锁 |
| 安全 | 无完整脱敏、无接口鉴权、无审计体系 |
| LLM | 无量控、无流式、无多模型路由 |
| 运维 | 无告警平台；LangSmith 非默认开启 |
| 产品 | 无多轮对话、无工单、无客服工作台 |
| 组织 | 无用户身份同步、无权限分级 |

详见本文档第 13 节「后续生产化建议」及 `docs/企业微信接入指南.md`。

---

## 7. 技术栈一览

| 层级 | 技术 |
|------|------|
| Web | FastAPI、Jinja2、Bootstrap 5 |
| 业务库 | MySQL 8.x |
| 向量库 | Qdrant（local） |
| Embedding | fastembed（BAAI/bge-small-zh-v1.5） |
| 编排 | LangGraph（8 节点） |
| LLM | LangChain + MockLLM / DeepSeek |
| 观测 | LangSmith（可选） |
| 企微 | 自研 Mock 层 + 回调预留 |

---

## 8. 核心页面索引

| 路径 | 说明 |
|------|------|
| `/` | 控制台首页 |
| `/ask-test` | 在线问答测试 + 反馈提交 |
| `/knowledge-cards` | 知识卡片列表 |
| `/knowledge-cards/new` | 新增知识卡片 |
| `/knowledge-cards/{id}` | 详情 / 编辑 / 审核 |
| `/unanswered-questions` | 未命中问题列表 |
| `/unanswered-questions/{id}` | 未命中详情（convert / ignore / 草稿） |
| `/question-logs` | 提问日志 |
| `/feedback` | 用户反馈列表 |
| `/statistics` | 统计看板 |

---

## 9. 核心 API 索引

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查（不依赖 DB） |
| POST | `/api/ask` | 问答主接口 |
| GET/POST | `/api/knowledge-cards` | 知识卡片 CRUD / 审核 / 向量同步 |
| GET/POST | `/api/unanswered-questions` | 未命中查询与沉淀操作 |
| POST/GET | `/api/feedback` | 反馈提交与列表 |
| GET | `/api/statistics/dashboard` | 统计看板数据 |
| GET | `/api/wecom/callback` | 企微 URL 验证 |
| POST | `/api/wecom/callback` | 企微真实 XML（`WECOM_ENABLED=false` 时 503） |
| POST | `/api/wecom/mock/callback` | 企微 Mock JSON（主验收入口） |

`/api/ask` 响应结构已冻结，不使用 `{success, data, message}` 包装。

---

## 10. 核心数据表职责

| 表名 | 职责 |
|------|------|
| `knowledge_card` | 知识卡片主数据、审核状态、向量状态 |
| `question_log` | 每次有效提问记录（含 `source_type`、`langsmith_trace_id`） |
| `unanswered_question` | 未命中问题汇聚与沉淀状态 |
| `feedback_log` | 用户对问答的反馈 |
| `tag` | 标签（预留扩展） |
| `system_config` | 系统配置键值 |

---

## 11. 最终验收脚本清单

完整顺序见 [`docs/验收清单.md`](验收清单.md#mvp-最终验收)。

| 脚本 | 用途 |
|------|------|
| `check_rag.py` | Qdrant 与检索（**服务停止时**执行） |
| `check_health.py` | 服务健康 |
| `check_db.py` | MySQL 与核心表 |
| `check_seed_data.py` | Seed 数据 |
| `check_graph.py` | LangGraph 主链路 |
| `check_llm.py` | LLM 生成 |
| `check_full_flow.py` | 端到端问答 |
| `check_unanswered_flow.py` | 未命中沉淀 |
| `check_feedback_stats.py` | 反馈与统计 |
| `check_langsmith.py` | LangSmith（关闭模式必过） |
| `check_wecom_mock.py` | 企微 Mock |

**全部退出码为 0** 即 MVP 验收通过。

---

## 12. 文档导航

| 文档 | 用途 |
|------|------|
| [本地启动说明.md](本地启动说明.md) | 本地启动一站式说明 |
| [演示脚本.md](演示脚本.md) | 领导版 / 技术版演示脚本 |
| [验收清单.md](验收清单.md) | 验收命令与通过标准 |
| [企业微信接入指南.md](企业微信接入指南.md) | 企业微信真实接入（生产向） |
| [架构决策.md](架构决策.md) | 架构决策与 MVP 边界 |
| [总阶段规划.md](总阶段规划.md) | 阶段总览与交付物索引 |
| [执行记录.md](执行记录.md) | 开发执行记录 |

---

## 13. 后续生产化建议（backlog，非当前阶段）

### P0 — 上线阻断项

1. 企业微信：完整 AES 加解密、HTTPS 公网、Redis `msg_id` 去重
2. 部署：Qdrant 集群或托管服务；多实例 + 共享向量库
3. 安全：问题/答案脱敏、API 鉴权、密钥托管

### P1 — 稳定性与可观测

1. DeepSeek 生产配置、token 监控、降级策略文档化
2. LangSmith 或等价 APM 默认策略、告警规则
3. 日志集中采集

### P2 — 产品增强

1. 流式回答、多轮对话
2. 批量知识导入、标签体系
3. 工单 / 客服系统对接

### P3 — 组织与运营

1. 用户身份与群维度统计
2. 权限分级与审核工作流增强

**以上不新增阶段十二**；需单独立项与确认后再开发。
