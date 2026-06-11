# 企业微信数字员工助手（digital-employee-assistant）

## MVP 已交付

面向企业微信实施群的知识沉淀型数字员工 **Demo / MVP**。阶段一至十一已全部完成，具备可演示、可脚本验收的完整业务闭环（问答 → 沉淀 → 反馈 → 统计）。

**定位**：可演示、可验收的 MVP，**不是**生产上线版本。无阶段十二；后续优化见交付文档中的生产化 backlog。

本地默认地址：`http://127.0.0.1:8001`（`.env` 中 `APP_PORT=8001`）

## 文档索引

| 文档 | 说明 |
|------|------|
| [docs/MVP_DELIVERY.md](docs/MVP_DELIVERY.md) | **交付总览**（能力、边界、验收、backlog） |
| [docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md) | **本地启动**（环境、seed、Qdrant、uvicorn） |
| [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) | **演示脚本**（领导版 15min / 技术版 25min） |
| [docs/ACCEPTANCE_CHECKLIST.md](docs/ACCEPTANCE_CHECKLIST.md) | **MVP 最终验收**命令与通过标准 |
| [docs/WECOM_INTEGRATION.md](docs/WECOM_INTEGRATION.md) | 企业微信真实接入（生产向） |
| [docs/DECISIONS.md](docs/DECISIONS.md) | 架构决策与 MVP 边界 |

## 快速启动

完整步骤见 [docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md)。摘要：

```powershell
cd F:\WorkSpace\digital-employee-assistant
.\.venv\Scripts\Activate.ps1

# 仅首次：Copy-Item .env.example .env（已有 .env 勿覆盖）

python scripts/seed_knowledge.py
python scripts/rebuild_qdrant.py --recreate   # 需先停 uvicorn
python scripts/check_rag.py

python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

## 演示与验收

- **演示**：[docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)
- **验收**：[docs/ACCEPTANCE_CHECKLIST.md#mvp-最终验收](docs/ACCEPTANCE_CHECKLIST.md#mvp-最终验收)

---

## 历史开发记录（阶段二至十一）

> 以下为分阶段开发过程文档，新用户请优先阅读 [MVP_DELIVERY.md](docs/MVP_DELIVERY.md)。技术栈：FastAPI、Jinja2、Bootstrap 5、MySQL、Qdrant、LangChain、LangGraph、DeepSeek、LangSmith。

### 环境要求

- Python 3.10 或 3.11（推荐）
- MySQL 8.x（阶段二起必需，需自行安装并启动）
- Windows / macOS / Linux 均可

阶段二起需要本地 MySQL；`/api/health` 仍不依赖数据库。

## 阶段二：MySQL 初始化

### 1. 安装并启动 MySQL

确保 MySQL 服务已运行，并确认 `.env` 中账号密码正确：

```text
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=root
MYSQL_DATABASE=digital_employee
```

### 2. 创建数据库

使用 MySQL 客户端执行：

```powershell
# 示例：mysql 命令行
mysql -u root -p < scripts/init_mysql.sql
```

或手动执行 `scripts/init_mysql.sql` 中的 `CREATE DATABASE` 语句。

### 3. 建表并写入 system_config 默认配置

```powershell
python app/db/init_db.py
```

### 4. 数据库验收

```powershell
python scripts/check_db.py
```

## 阶段三：知识卡片与演示数据

### 1. 导入演示数据（推荐）

```powershell
python scripts/seed_knowledge.py
```

脚本按 `title` 幂等去重，可重复执行。

### 2. 种子数据验收

```powershell
python scripts/check_seed_data.py
```

期望：`approved + enabled` 知识卡片不少于 5 条。

### 3. 知识卡片页面

| 路径 | 说明 |
|------|------|
| `/knowledge-cards` | 列表（含操作按钮） |
| `/knowledge-cards/new` | 新增 |
| `/knowledge-cards/{id}` | 详情 |
| `/knowledge-cards/{id}/edit` | 编辑 |

### 4. 知识卡片 API

| 方法 | 路径 |
|------|------|
| GET | `/api/knowledge-cards` |
| GET | `/api/knowledge-cards/{id}` |
| POST | `/api/knowledge-cards` |
| PUT | `/api/knowledge-cards/{id}` |
| POST | `/api/knowledge-cards/{id}/audit` |
| POST | `/api/knowledge-cards/{id}/enable` |
| POST | `/api/knowledge-cards/{id}/disable` |
| DELETE | `/api/knowledge-cards/{id}` |

| POST | `/api/knowledge-cards/{id}/sync-vector` |

### 5. 状态说明

- 新建默认：`draft`
- 提交审核：`draft/rejected` → `pending`
- 审核通过/拒绝：仅 `pending` 可操作
- 已 `approved` 编辑后：保持 `approved`，`version+1`，`vector_status=pending`
- 删除为逻辑删除：`deleted=1`，`enabled=0`

## 阶段十一：企业微信接口预留

### 1. 重要说明

- **Mock 验收**：`POST /api/wecom/mock/callback`（JSON）为本地主入口，默认 `WECOM_MOCK_ENABLED=true`
- **真实回调预留**：`GET/POST /api/wecom/callback`；`WECOM_ENABLED=false` 时 POST 返回 503，不影响 Web 与 `/api/ask`
- **复用链路**：`WecomCallbackService` → `AskService` → LangGraph，不新建第二套问答服务
- **source_type**：企业微信入口固定 `source_type=wecom` 写入 `question_log`
- **去重**：进程内 TTL（`WECOM_DEDUP_TTL_SECONDS`），重启 uvicorn 后缓存清空；多实例需 Redis（本阶段不做）
- **WECOM_BOT_KEY**：仅文档说明用于未来主动发送，**不用于接收回调**
- **加解密**：AES 完整实现未就绪，生产前见 `docs/WECOM_INTEGRATION.md`

### 2. 企业微信配置（`.env`）

```text
WECOM_ENABLED=false
WECOM_MOCK_ENABLED=true
WECOM_CORP_ID=
WECOM_AGENT_ID=
WECOM_SECRET=
WECOM_TOKEN=
WECOM_ENCODING_AES_KEY=
WECOM_BOT_KEY=
WECOM_CALLBACK_PATH=/api/wecom/callback
WECOM_DEDUP_TTL_SECONDS=86400
```

### 3. 回调路径

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/wecom/callback` | URL 验证（Mock：直接返回 echostr） |
| POST | `/api/wecom/callback` | 真实 XML 回调预留 |
| POST | `/api/wecom/mock/callback` | JSON Mock 验收主入口 |

### 4. 阶段十一验收

```powershell
python scripts/check_wecom_mock.py
python scripts/check_langsmith.py
python scripts/check_feedback_stats.py
python scripts/check_graph.py
python scripts/check_full_flow.py
```

## 阶段十：LangSmith 观测

### 1. 重要说明

- **默认关闭**：`LANGSMITH_TRACING=false`；无 `LANGSMITH_API_KEY` 时 `is_langsmith_enabled=false`，问答照常运行
- **开启方式**：设置 `LANGSMITH_TRACING=true` 并填写 `LANGSMITH_API_KEY`，重启 uvicorn 后生效
- **隐私**：默认 `LANGSMITH_HIDE_INPUTS=true`、`LANGSMITH_HIDE_OUTPUTS=true`；仅向 LangSmith 发送安全 metadata（问题长度、命中率、耗时等），不发送问题/答案全文
- **trace_id**：写入 `question_log.langsmith_trace_id`，**不**返回给前端
- **降级**：LangSmith 导入失败、Key 错误、网络超时、trace 落库失败等均只打 WARN，自动降级为普通 `graph.invoke`，**不会**导致 `/api/ask` 500
- **不接企业微信**；不改 `/api/ask` 响应结构；不改数据库表结构

### 2. LangSmith 配置（`.env`）

```text
LANGSMITH_TRACING=false
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=digital-employee-assistant
LANGSMITH_ENDPOINT=
LANGSMITH_HIDE_INPUTS=true
LANGSMITH_HIDE_OUTPUTS=true
```

> 请勿将 `LANGSMITH_API_KEY` 提交到 Git。`LANGSMITH_ENDPOINT` 可选，用于私有化 / 自托管 LangSmith。

### 3. 阶段十验收

```powershell
# 停服务后准备（Qdrant 单实例）
python scripts/seed_knowledge.py
python scripts/rebuild_qdrant.py --recreate
python scripts/check_rag.py

# 终端 1：单实例 uvicorn
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

# 终端 2
python scripts/check_langsmith.py
python scripts/check_feedback_stats.py
python scripts/check_unanswered_flow.py
python scripts/check_graph.py
python scripts/check_llm.py
python scripts/check_full_flow.py
python scripts/check_health.py
python scripts/check_seed_data.py
python scripts/check_db.py
```

可选开启模式（需重启服务）：

```text
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=你的Key
LANGSMITH_PROJECT=digital-employee-assistant
LANGSMITH_HIDE_INPUTS=true
LANGSMITH_HIDE_OUTPUTS=true
```

## 阶段九：反馈 + 统计看板增强

### 1. 重要说明

- `/ask-test` 支持「有用 / 无用 / 需要人工处理」反馈
- 每个 `question_log_id` 仅允许提交 **1 次**反馈
- `need_human` 不计入满意度分母
- 统计看板新增：未命中率、满意度、Top 未命中、Top 负反馈
- 不接企业微信、不接 LangSmith、不改 `/api/ask` 响应

### 2. 反馈 API

| 方法 | 路径 |
|------|------|
| POST | `/api/feedback` |
| GET | `/api/feedback` |
| GET | `/api/statistics/dashboard` |

### 3. 阶段九验收

```powershell
python scripts/check_feedback_stats.py
python scripts/check_unanswered_flow.py
python scripts/check_graph.py
```

## 阶段八：未命中问题沉淀闭环

### 1. 重要说明

- 未命中问题支持 **pending → converted / ignored** 状态流转（终态不可回退）
- **convert** 创建 `audit_status=draft` 知识卡片，**不**同步 Qdrant
- **generate-draft** 仅 AI/Mock 预览，不落库
- draft 需人工 **submit_audit → audit approved** 后，沿用阶段五 `VectorSyncService` 同步
- `converted` / `ignored` 后同题再未命中会**新建 pending** 记录
- 不接企业微信、不接 LangSmith、不改 `/api/ask` 响应

### 2. 未命中 API

| 方法 | 路径 |
|------|------|
| GET | `/api/unanswered-questions` |
| GET | `/api/unanswered-questions/{id}` |
| POST | `/api/unanswered-questions/{id}/generate-draft` |
| POST | `/api/unanswered-questions/{id}/convert` |
| POST | `/api/unanswered-questions/{id}/ignore` |

### 3. 阶段八验收

```powershell
python scripts/check_unanswered_flow.py
python scripts/check_graph.py
python scripts/check_full_flow.py
```

## 阶段七：LangGraph 工作流编排

### 1. 重要说明

- 阶段七**只做流程编排**，不重写 Qdrant 检索与 LLM 生成
- 节点薄封装：`RetrievalService`、`AnswerGenerationService`、`AskLogService`
- **不接 LangSmith**、不做多 Agent、不做问题改写、不做高风险识别
- `AskResponse` 响应结构与阶段六完全一致
- Qdrant local 模式仍要求**单实例 uvicorn**，勿多进程同时访问

### 2. Graph 节点

`validate_input` → `preprocess_question` → `retrieve` → `match_judge` → `generate_answer` / `handle_miss` / `error_fallback` → `write_log`

### 3. 阶段七验收

**停服务后准备数据：**

```powershell
python scripts/seed_knowledge.py
python scripts/rebuild_qdrant.py --recreate
python scripts/check_rag.py
```

**终端 1：启动单实例服务**

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

**终端 2：验收**

```powershell
python scripts/check_graph.py
python scripts/check_llm.py
python scripts/check_full_flow.py
python scripts/check_health.py
python scripts/check_seed_data.py
python scripts/check_db.py
```

阶段七主验收脚本为 `check_graph.py`。

## 阶段六：LangChain + DeepSeek / MockLLM

### 1. 重要说明

- 默认 `LLM_PROVIDER=mock`，**没有 DeepSeek Key 也能完整演示**
- DeepSeek Key 只放在 `.env` 的 `DEEPSEEK_API_KEY`，**不要写进代码**
- DeepSeek 调用失败会自动降级 MockLLM 或模板回答
- 阶段六**仍保留 Qdrant 检索**，只改变命中后的答案生成方式
- 仍不接 LangGraph / LangSmith

### 2. LLM 配置

```text
LLM_PROVIDER=mock
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
LLM_TIMEOUT=30
LLM_MAX_TOKENS=2048
```

### 3. 阶段六验收

```powershell
python scripts/rebuild_qdrant.py --recreate
python scripts/check_rag.py
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
python scripts/check_llm.py
python scripts/check_full_flow.py
```

## 阶段五：Embedding + Qdrant

### 1. 重要说明

- **fastembed 首次运行可能需要下载模型**（需联网，耗时数分钟）
- Qdrant 使用 **local mode**，数据目录 `./storage/qdrant`
- **`storage/qdrant` 不提交 Git**（已在 `.gitignore` 忽略）
- 阶段五仍不接 DeepSeek / LangGraph / LangSmith
- 答案仍是知识卡片字段拼接，**不是 LLM 生成**

### 2. 首次使用（必须先重建向量库）

```powershell
python scripts/seed_knowledge.py
python scripts/rebuild_qdrant.py --recreate
python scripts/check_rag.py
```

### 3. 向量同步规则

仅 `deleted=0` 且 `audit_status=approved` 且 `enabled=1` 的卡片进入 Qdrant。

触发时机：审核通过、启用、编辑 approved 卡片、停用、删除、手动 `sync-vector`。

### 4. 阶段五验收

```powershell
python scripts/rebuild_qdrant.py --recreate
python scripts/check_rag.py
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
python scripts/check_full_flow.py
```

## 阶段四：在线测试与假问答（已完成）

### 1. 历史说明

阶段四使用规则匹配；阶段五已切换为 Qdrant 向量检索。

### 2. 在线测试页面

| 路径 | 说明 |
|------|------|
| `/ask-test` | 在线测试页面 |

### 3. 提问 API

```http
POST /api/ask
Content-Type: application/json

{
  "question": "客户现场登录失败，提示账号无权限，应该怎么处理？",
  "user_id": "zhangsan",
  "group_id": "demo_group",
  "source_type": "web"
}
```

返回为专用结构（不使用 `{success,data,message}` 包装）。

### 4. 阶段四验收

**终端 1：启动服务**

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

**终端 2：完整流程验收**

```powershell
python scripts/check_full_flow.py
```

演示问题：

- 命中：`客户现场登录失败，提示账号无权限，应该怎么处理？`
- 未命中：`客户打印模板套打偏移怎么处理？`

## 阶段一：启动步骤

### 1. 进入项目目录

```powershell
cd F:\WorkSpace\digital-employee-assistant
```

### 2. 创建并激活虚拟环境（推荐）

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. 安装依赖

```powershell
pip install -r requirements.txt
```

首次安装会拉取 LangChain、Qdrant 等后续阶段依赖，可能需要几分钟。

### 4. 复制环境变量

```powershell
copy .env.example .env
```

阶段一使用默认配置即可，无需配置 MySQL 或 DeepSeek Key。

### 5. 启动服务

在项目根目录、已激活虚拟环境的前提下执行（**Windows 推荐用 `python -m uvicorn`**）：

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

端口需与 `.env` 中 `APP_PORT` 一致（当前默认 `8001`）。若直接敲 `uvicorn` 无法启动，请改用上面的 `python -m uvicorn` 形式。

## 访问地址

| 地址 | 说明 |
|------|------|
| http://127.0.0.1:8001/ | 后台首页 / 控制台 |
| http://127.0.0.1:8001/ask-test | 在线测试 |
| http://127.0.0.1:8001/knowledge-cards | 知识卡片列表 |
| http://127.0.0.1:8001/unanswered-questions | 未命中问题列表 |
| http://127.0.0.1:8001/question-logs | 提问日志列表 |
| http://127.0.0.1:8001/feedback | 用户反馈列表 |
| http://127.0.0.1:8001/statistics | 统计看板 |
| http://127.0.0.1:8001/api/health | 健康检查 JSON |

健康检查期望返回：

```json
{
  "status": "ok",
  "module": "digital-employee-assistant",
  "env": "dev"
}
```

## 阶段一：验收命令

在**服务已启动**的前提下，另开一个终端执行：

```powershell
cd F:\WorkSpace\digital-employee-assistant
python scripts/check_health.py
```

也可手动验证：

```powershell
curl http://127.0.0.1:8001/
curl http://127.0.0.1:8001/api/health
```

## 阶段十一验收标准

1. `python scripts/check_wecom_mock.py` 退出码为 0
2. Mock 命中/未命中/去重/空问题断言通过
3. `question_log.source_type=wecom` 正确落库
4. `WECOM_ENABLED=false` 时服务正常启动；`POST /api/wecom/callback` 返回 503
5. `/api/ask` 与 `/ask-test` 行为不变；阶段七至十回归脚本仍通过

## 阶段十验收标准

1. `python scripts/check_langsmith.py` 退出码为 0（关闭模式必过；有 Key 时额外验证 enabled 模式）
2. 关闭 tracing 时 `question_log.langsmith_trace_id` 为 `null`
3. 开启 tracing 且 Key 有效时 `langsmith_trace_id` 非空（仅落库，不返回前端）
4. LangSmith 异常不影响 `/api/ask` 正常返回
5. 阶段七至九回归脚本仍通过

## 阶段九验收标准

1. `python scripts/check_feedback_stats.py` 退出码为 0
2. 每条 `question_log_id` 仅可反馈一次；空问题不可反馈
3. 统计看板含命中率/未命中率/满意度/Top 榜单
4. 阶段七至八回归脚本仍通过

## 阶段八验收标准

1. `python scripts/check_unanswered_flow.py` 退出码为 0
2. pending 可 generate-draft、convert、ignore
3. convert 后 `status=converted` 且知识卡片为 `draft`
4. draft 审核前不同步 Qdrant；approved 后沿用阶段五同步
5. 阶段七回归脚本仍通过

## 阶段七验收标准

1. `python scripts/check_graph.py` 退出码为 0（主验收）
2. 命中 / 未命中 / 空问题路径与阶段六一致
3. `python scripts/check_llm.py` 与 `python scripts/check_full_flow.py` 仍通过
4. Qdrant 检索与 LLM 生成 Service 逻辑未重写；`AskResponse` 结构不变

## 阶段六验收标准

1. `LLM_PROVIDER=mock` 时 `python scripts/check_llm.py` 退出码为 0
2. 命中 answer 含「答案来源」，不含「阶段五模拟回答」
3. mock 模式 answer 含「Mock 模型回答」
4. 未命中不调用 LLM，逻辑与阶段五一致
5. `python scripts/check_full_flow.py` 与 `python scripts/check_rag.py` 仍通过

## 阶段五验收标准

1. `python scripts/rebuild_qdrant.py --recreate` 退出码为 0
2. `python scripts/check_rag.py` 退出码为 0
3. `/ask-test` 命中问题返回真实 `similarity_score`（非固定 0.86）
4. 停用已同步卡片后 Qdrant 向量被删除，重新启用后可再同步
5. `python scripts/check_full_flow.py` 退出码为 0

## 阶段四验收标准

1. `/ask-test` 页面可提问并展示结果
2. 命中问题 `matched=true` 且有 `sources`
3. 未命中问题写入 `unanswered_question`，重复提问 `frequency` 增加
4. `python scripts/check_full_flow.py` 退出码为 0

## 阶段三验收标准

1. `python scripts/seed_knowledge.py` 可导入 5 条演示数据
2. `python scripts/check_seed_data.py` 退出码为 0
3. 页面可新增、编辑、详情、提交审核、审核通过/拒绝、启用/停用、删除
4. API 与页面共用 `KnowledgeService`，无 Qdrant 调用

## 阶段二验收标准

1. `python app/db/init_db.py` 成功建表
2. `python scripts/check_db.py` 退出码为 0，输出 6 张核心表
3. 5 个列表/统计页面空数据时不报错
4. `/api/health` 仍返回 `status=ok`（回归阶段一）

## 阶段一验收标准

1. 首页可访问，左侧菜单与顶部 Provider 状态正常显示
2. `/api/health` 返回 `status=ok`
3. `python scripts/check_health.py` 退出码为 0
4. 预留目录 `app/agent`、`app/rag`、`app/llm`、`app/security`、`app/prompts` 已创建

## 目录结构（阶段一）

```text
digital-employee-assistant/
├── app/
│   ├── main.py
│   ├── config/settings.py
│   ├── routers/
│   ├── templates/
│   ├── static/
│   ├── agent/          # 预留
│   ├── rag/            # 预留
│   ├── llm/            # 预留
│   ├── security/       # 预留
│   └── prompts/        # 预留
├── scripts/check_health.py
├── requirements.txt
├── .env.example
└── README.md
```

## 常见问题

**Q: 启动时报找不到模块 `app`，或 `uvicorn` 不是内部命令？**  
A: 请在项目根目录执行，并使用 `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001`，不要进入 `app/` 子目录。

**Q: `check_health.py` 连接失败？**  
A: 请先启动服务，并确认 `.env` 中 `APP_PORT` 与启动时 `--port` 参数一致（当前为 `8001`）。

**Q: 列表页提示数据库连接失败？**  
A: 请确认 MySQL 已启动、已执行 `init_mysql.sql` 建库，并运行 `python app/db/init_db.py`。

**Q: 是否需要安装 MySQL？**  
A: 阶段二起需要。请安装 MySQL 8.x 并配置 `.env` 中的 `MYSQL_*`。
