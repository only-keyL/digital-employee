# 验收清单

> 每阶段完成后按顺序执行对应命令。全部通过后再更新 `STAGE_CONTROL.md` 进入下一阶段。

## 通用准备

```powershell
cd F:\WorkSpace\digital-employee-assistant
.\.venv\Scripts\Activate.ps1
```

本地服务默认地址：`http://127.0.0.1:8001`

---

## 阶段一：项目骨架

### 验收命令

```powershell
# 终端 1：启动服务
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

# 终端 2
python scripts/check_health.py
```

### 通过标准

- [ ] `check_health.py` 退出码为 0
- [ ] 返回 `status=ok`
- [ ] 首页与健康检查页面可访问

---

## 阶段二：MySQL + 基础表结构 + 只读列表页

### 验收命令

```powershell
python scripts/init_db.py   # 首次或表结构变更时
python scripts/check_db.py
```

### 通过标准

- [ ] MySQL 连接成功
- [ ] 数据库 `digital_employee` 存在
- [ ] 6 张核心表存在：`knowledge_card`、`question_log`、`unanswered_question`、`feedback_log`、`tag`、`system_config`
- [ ] `check_db.py` 退出码为 0

---

## 阶段三：知识卡片 CRUD + Seed 数据

### 验收命令

```powershell
python scripts/seed_knowledge.py
python scripts/check_seed_data.py
```

### 通过标准

- [ ] Seed 可幂等导入演示数据
- [ ] 存在 `approved + enabled` 的知识卡片
- [ ] `check_seed_data.py` 退出码为 0
- [ ] 页面可完成新增、编辑、审核、启停、删除（逻辑删除）

---

## 阶段四：在线测试页面 + 假问答流程

### 验收命令

```powershell
# 终端 1：确保 seed 后启动服务
python scripts/seed_knowledge.py
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

# 终端 2
python scripts/check_full_flow.py
python scripts/check_health.py
python scripts/check_seed_data.py
python scripts/check_db.py
```

### 通过标准

- [ ] `/ask-test` 页面可提问并展示结果
- [ ] 命中问题：`matched=true`，`sources` 非空，`question_log_id` 非空
- [ ] 未命中问题：`matched=false`，`fallback_reason` 非空，写入 `unanswered_question`
- [ ] 重复未命中问题 `frequency` 递增
- [ ] 空问题不写 `question_log`，`question_log_id=null`
- [ ] `check_full_flow.py` 退出码为 0

### 演示问题

- 命中：`客户现场登录失败，提示账号无权限，应该怎么处理？`
- 未命中：`客户打印模板套打偏移怎么处理？`

---

## 阶段五：Embedding + Qdrant 接入

### 验收命令

```powershell
# 终端 1：启动服务（阶段五实施后）
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

# 终端 2
python scripts/rebuild_qdrant.py
python scripts/check_rag.py
```

### 通过标准

- [ ] 首次执行 `python scripts/rebuild_qdrant.py --recreate` 退出码为 0
- [ ] `python scripts/check_rag.py` 退出码为 0
- [ ] Qdrant local collection 存在且有点向量
- [ ] approved+enabled 卡片 `vector_status=synced`
- [ ] `/api/ask` 使用 Qdrant 检索，命中返回真实 similarity_score
- [ ] 停用 / 删除卡片时向量被移除，重新启用可再同步
- [ ] `python scripts/check_full_flow.py` 退出码为 0
- [ ] 仍不接 DeepSeek、LangGraph、LLM 生成答案

### 注意事项

- fastembed 首次运行需下载模型（需联网）
- `storage/qdrant` 不提交 Git

---

## 阶段六：LangChain + DeepSeek / MockLLM

### 验收命令

```powershell
# 终端 1
python scripts/seed_knowledge.py
python scripts/rebuild_qdrant.py --recreate
python scripts/check_rag.py
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

# 终端 2（默认 LLM_PROVIDER=mock）
python scripts/check_llm.py
python scripts/check_full_flow.py
python scripts/check_health.py
python scripts/check_seed_data.py
python scripts/check_db.py
```

### 通过标准

- [ ] `check_llm.py` 退出码为 0
- [ ] 命中 answer 含「答案来源」，不含「阶段五模拟回答」
- [ ] mock 模式 answer 含「Mock 模型回答」
- [ ] 未命中不调用 LLM，`unanswered_question` 逻辑不变
- [ ] DeepSeek 失败自动降级，接口不返回 500
- [ ] 仍保留 Qdrant 检索；`check_rag.py` 仍通过

### 配置说明

- 默认 `LLM_PROVIDER=mock`
- `DEEPSEEK_API_KEY` 只放 `.env`，不写进代码

---

## 阶段七：LangGraph 工作流编排

### 验收命令

```powershell
# 停服务后准备
python scripts/seed_knowledge.py
python scripts/rebuild_qdrant.py --recreate
python scripts/check_rag.py

# 终端 1：单实例 uvicorn
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

# 终端 2
python scripts/check_graph.py
python scripts/check_llm.py
python scripts/check_full_flow.py
python scripts/check_health.py
python scripts/check_seed_data.py
python scripts/check_db.py
```

### 通过标准

- [ ] `check_graph.py` 退出码为 0（阶段七主验收）
- [ ] 命中：`matched=true`，`sources` 非空，`answer` 含「答案来源」，不含「阶段五模拟回答」
- [ ] mock 模式命中 answer 含「Mock 模型回答」
- [ ] 未命中：`matched=false`，`fallback_reason` 非空，写入 `unanswered_question`
- [ ] 空问题：`question_log_id=null`，`fallback_reason` 含「问题不能为空」
- [ ] 检索异常不写 `unanswered_question`，写 `question_log`
- [ ] `check_llm.py`、`check_full_flow.py`、`check_rag.py` 仍通过
- [ ] 不接 LangSmith、多 Agent、问题改写、高风险识别

### 注意事项

- Qdrant local 勿多 uvicorn 进程同时访问
- 服务运行中勿执行 `rebuild_qdrant.py --recreate`

---

## 阶段八：未命中问题沉淀闭环

### 验收命令

```powershell
# 停服务后准备
python scripts/seed_knowledge.py
python scripts/rebuild_qdrant.py --recreate
python scripts/check_rag.py

# 终端 1：单实例 uvicorn
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

# 终端 2
python scripts/check_unanswered_flow.py
python scripts/check_graph.py
python scripts/check_llm.py
python scripts/check_full_flow.py
python scripts/check_health.py
python scripts/check_seed_data.py
python scripts/check_db.py
```

### 通过标准

- [ ] `check_unanswered_flow.py` 退出码为 0（阶段八主验收）
- [ ] pending 可 generate-draft、convert、ignore
- [ ] convert 后 `status=converted`，`convert_card_id` 非空，知识卡片 `audit_status=draft`
- [ ] draft 审核前不同步 Qdrant；approved 后 `vector_status=synced`
- [ ] ignore 后 `status=ignored` 为终态
- [ ] converted/ignored 后同题再未命中新建 pending
- [ ] `/api/ask` 响应结构不变；阶段七回归脚本仍通过

---

## 阶段九：反馈 + 统计看板增强

### 验收命令

```powershell
# 停服务后准备
python scripts/seed_knowledge.py
python scripts/rebuild_qdrant.py --recreate
python scripts/check_rag.py

# 终端 1：单实例 uvicorn
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

# 终端 2
python scripts/check_feedback_stats.py
python scripts/check_unanswered_flow.py
python scripts/check_graph.py
python scripts/check_llm.py
python scripts/check_full_flow.py
python scripts/check_health.py
python scripts/check_seed_data.py
python scripts/check_db.py
```

### 通过标准

- [ ] `check_feedback_stats.py` 退出码为 0（阶段九主验收）
- [ ] `/ask-test` 可提交 useful/useless/need_human 反馈
- [ ] 同一 `question_log_id` 重复反馈被拒绝
- [ ] 空问题 `question_log_id=null` 时反馈按钮禁用
- [ ] `/statistics` 与 `/api/statistics/dashboard` 含完整指标
- [ ] `need_human` 不计入满意度分母
- [ ] 阶段七至八回归脚本仍通过

---

## 阶段十：LangSmith 观测

### 准备

```powershell
cd F:\WorkSpace\digital-employee-assistant
.\.venv\Scripts\Activate.ps1

python scripts/seed_knowledge.py
python scripts/rebuild_qdrant.py --recreate
python scripts/check_rag.py
```

### 启动服务（单实例）

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

### 验收命令（另一终端）

```powershell
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

### 可选：开启 LangSmith

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=你的Key
LANGSMITH_PROJECT=digital-employee-assistant
LANGSMITH_HIDE_INPUTS=true
LANGSMITH_HIDE_OUTPUTS=true
```

重启 uvicorn 后再次执行 `python scripts/check_langsmith.py`。

### 通过标准

- [ ] `check_langsmith.py` 退出码为 0（关闭模式必过）
- [ ] 关闭 tracing 时 `question_log.langsmith_trace_id` 为 `null`
- [ ] 有 Key 且开启时 `langsmith_trace_id` 非空（仅落库）
- [ ] LangSmith 异常不影响 `/api/ask` 返回
- [ ] `/api/ask` 响应结构未变；trace_id 不返回前端
- [ ] 阶段七至九回归脚本仍通过

---

## 阶段十一：企业微信接口预留

### 准备

```powershell
cd F:\WorkSpace\digital-employee-assistant
.\.venv\Scripts\Activate.ps1

python scripts/seed_knowledge.py
python scripts/rebuild_qdrant.py --recreate
python scripts/check_rag.py
```

### 启动服务（单实例）

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

### 验收命令（另一终端）

```powershell
python scripts/check_wecom_mock.py
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

### 通过标准

- [ ] `check_wecom_mock.py` 退出码为 0（阶段十一主验收）
- [ ] Mock URL 验证返回 echostr
- [ ] Mock 命中返回 XML，含「答案来源」或「Mock 模型回答」
- [ ] `question_log.source_type=wecom`
- [ ] 相同 `msg_id` 重复回调不新增 `question_log`
- [ ] 未命中写入 `unanswered_question`
- [ ] 空问题不写 `question_log`
- [ ] `POST /api/wecom/callback` 在 `WECOM_ENABLED=false` 时返回 503
- [ ] `/api/ask` 与 `/ask-test` 不受影响；阶段七至十回归通过

### 真实企业微信（可选，人工）

见 `docs/WECOM_INTEGRATION.md`，需公网域名与后台配置，非自动化验收项。
