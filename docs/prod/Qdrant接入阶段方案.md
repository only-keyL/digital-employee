------

# 一、整体阶段策略

你现在的 Qdrant 阶段可以调整成 4 步：

```text
阶段 A：开发测试阶段 —— 使用 Qdrant Cloud
阶段 B：代码抽象阶段 —— 屏蔽 Cloud / Self-host 差异
阶段 C：预生产迁移阶段 —— 服务器自建 Qdrant 并做数据迁移
阶段 D：生产上线阶段 —— 切换到服务器 Qdrant，Cloud 只保留短期备份
```

核心原则：

```text
开发测试阶段不装 Qdrant。
代码里不写死 Cloud。
所有连接信息全部走环境变量。
正式上线前必须完成自建 Qdrant 验收。
```

------

# 二、阶段 A：开发测试阶段使用 Qdrant Cloud

## 目标

先让你的 RAG 闭环真实跑起来：

```text
知识卡片审核通过
  ↓
生成 embedding
  ↓
写入 Qdrant Cloud
  ↓
用户提问
  ↓
Qdrant Cloud 检索
  ↓
DeepSeek 生成答案
  ↓
写入问答日志
```

这个阶段重点不是部署能力，而是验证：

```text
1. 向量写入是否正常。
2. 相似度检索是否正常。
3. TopK 召回是否合理。
4. 问答链路是否稳定。
5. 知识卡片字段是否适合向量化。
```

## 需要准备

你需要在 Qdrant Cloud 创建一个 Free Cluster，然后拿到：

```env
QDRANT_URL=https://你的-qdrant-cloud-cluster-url
QDRANT_API_KEY=你的QdrantCloudKey
QDRANT_COLLECTION=digital_employee_knowledge_dev
QDRANT_MODE=remote
QDRANT_DEPLOYMENT=cloud
```

Qdrant Cloud 支持通过 Database API Key 连接集群，并且 Cloud API 也支持管理集群、备份计划、认证等能力。([Qdrant](https://qdrant.tech/documentation/cloud/authentication/?utm_source=chatgpt.com))

## 开发测试阶段限制

这里非常关键：

```text
1. 不要上传公司真实敏感知识。
2. 使用脱敏后的实施问题。
3. 客户名、账号、合同金额、数据库地址、密钥全部替换。
4. collection 名称必须带 dev/test 后缀。
5. 不要把 dev/test collection 当成生产库。
```

建议 collection 命名：

```text
digital_employee_knowledge_dev
digital_employee_knowledge_test
```

不要用：

```text
digital_employee_knowledge_prod
```

## Cursor 执行范围

这一阶段让 Cursor 只做：

```text
1. 接入 Qdrant Cloud。
2. 新增 Qdrant 连接配置。
3. 新增 check_qdrant_cloud.py。
4. 支持 collection 创建。
5. 支持 upsert 测试向量。
6. 支持 search 测试向量。
```

不要让 Cursor 做：

```text
1. 不要本地 Docker 部署 Qdrant。
2. 不要写生产 docker-compose。
3. 不要改企微真实回调。
4. 不要改复杂 LangGraph。
```

## 验收标准

```text
1. check_qdrant_cloud.py 执行成功。
2. 能创建 digital_employee_knowledge_dev collection。
3. 能写入 1 条测试知识向量。
4. 能用问题检索出这条知识。
5. FastAPI 启动时能检测 Qdrant Cloud 连接。
6. QDRANT_API_KEY 不允许打印到日志。
```

------

# 三、阶段 B：代码抽象，避免后期迁移返工

## 目标

你后面要从 Qdrant Cloud 切换到服务器自建 Qdrant，所以现在必须把代码设计成：

```text
业务代码不关心 Qdrant 部署在哪里。
```

也就是说，AskGraph、知识同步任务、后台页面都不能直接依赖具体的 Cloud URL。

## 推荐抽象

新增这一层：

```text
app/rag/vector_store_base.py
app/rag/qdrant_store.py
app/rag/qdrant_client_factory.py
app/rag/vector_payload_builder.py
```

抽象接口：

```python
class VectorStore:
    def ensure_collection(self) -> None:
        pass

    def upsert_knowledge(self, knowledge_card) -> None:
        pass

    def delete_knowledge(self, knowledge_id: int) -> None:
        pass

    def search(self, query_text: str, top_k: int) -> list[dict]:
        pass
```

具体实现：

```text
QdrantVectorStore
  - Qdrant Cloud 使用它
  - 自建 Qdrant 也使用它
  - 区别只在 QDRANT_URL / QDRANT_API_KEY / COLLECTION
```

你不需要写两个完全不同的 Store。Cloud 和自建 Qdrant 的 HTTP/gRPC 接口是一致的，核心差异是连接地址、认证方式、网络位置。

## 环境变量设计

建议统一这样写：

```env
VECTOR_PROVIDER=qdrant

QDRANT_MODE=remote
QDRANT_DEPLOYMENT=cloud
QDRANT_URL=https://xxxx.cloud.qdrant.io
QDRANT_API_KEY=xxxx
QDRANT_COLLECTION=digital_employee_knowledge_dev

QDRANT_TOP_K=5
QDRANT_SCORE_THRESHOLD=0.65
QDRANT_TIMEOUT_SECONDS=5
```

后期服务器自建只改成：

```env
QDRANT_MODE=remote
QDRANT_DEPLOYMENT=self_hosted
QDRANT_URL=http://qdrant.internal:6333
QDRANT_API_KEY=公司内网QdrantKey
QDRANT_COLLECTION=digital_employee_knowledge_prod
```

## 重点设计

你现在就要避免这类写法：

```python
client = QdrantClient(path="./storage/qdrant")
```

也不要在业务代码里写死：

```python
client = QdrantClient(url="https://xxx")
```

正确方式是：

```python
client = qdrant_client_factory.create_client(settings)
```

这样后期迁移不会动业务代码。

## 验收标准

```text
1. AskService 不直接创建 QdrantClient。
2. VectorSyncWorker 不直接创建 QdrantClient。
3. 所有 Qdrant 连接都走 qdrant_client_factory。
4. 切换 Cloud / Self-host 只需要改 .env。
5. collection payload 结构保持一致。
```

------

# 四、阶段 C：向量同步任务化，Cloud 和自建都复用

## 目标

不要让“审核知识卡片”这个动作直接同步 Qdrant。

正确流程应该是：

```text
审核通过知识卡片
  ↓
MySQL 写入 vector_sync_task
  ↓
后台 worker 消费任务
  ↓
生成 embedding
  ↓
upsert 到 Qdrant
  ↓
更新 vector_status = synced
```

你的生产 V1 方案里也已经明确要求通过任务表保障知识同步可靠性，并且 Qdrant remote 是第一批基础设施真实化的一部分。

## 为什么必须这样做

因为开发阶段你用 Cloud，生产阶段你用自建 Qdrant。网络、权限、延迟、失败场景都会变化。

如果你直接在审核接口里同步 Qdrant，会出现：

```text
1. Qdrant 慢，审核页面卡死。
2. Qdrant 失败，知识审核状态混乱。
3. 迁移期间无法批量重试。
4. Cloud 切自建时不好补数据。
```

任务化之后就简单：

```text
Cloud 不稳定 → task failed → 重试
自建 Qdrant 初始化 → 批量重跑 task
迁移后缺数据 → 从 MySQL 全量重建向量
```

## 需要新增

```text
vector_sync_task 表
vector_sync_task_repository.py
vector_sync_task_service.py
vector_sync_worker.py
scripts/check_vector_sync_task.py
scripts/rebuild_qdrant_collection.py
```

## 任务状态

```text
pending
running
success
failed
```

## 任务类型

```text
upsert
delete
disable
rebuild
```

## 验收标准

```text
1. 审核通过只生成 pending 任务，不直接阻塞同步。
2. worker 能把 pending 任务同步到 Qdrant Cloud。
3. 同步成功后 knowledge_card.vector_status=synced。
4. 同步失败后记录 error_message。
5. 支持从 MySQL approved 知识全量重建 collection。
```

------

# 五、阶段 D：预生产阶段自建 Qdrant Server

## 目标

在正式上线前，把 Qdrant 从 Cloud 切换到公司服务器。

注意：我建议你不要“正式上线之后再部署自建 Qdrant”，而是：

```text
开发测试：Qdrant Cloud
预生产：服务器自建 Qdrant
正式上线：服务器自建 Qdrant
```

原因是：正式上线之后再迁移，会涉及真实知识数据、企微真实流量、用户反馈链路，风险更高。更稳妥的做法是上线前完成迁移演练。

Qdrant 官方支持 Docker 方式本地运行，常规暴露端口是 6333/6334，并且可以挂载本地目录做持久化。([Qdrant](https://qdrant.tech/documentation/quickstart/?utm_source=chatgpt.com)) 自建 Qdrant 还需要注意安全，官方文档说明 Qdrant 支持静态 API Key 认证，也有专门的自建安全加固文档建议启用 TLS、API Key、限制访问来源。([Qdrant](https://qdrant.tech/documentation/security/?utm_source=chatgpt.com))

## 服务器准备

推荐最低配置：

```text
2C4G Linux 服务器
Docker
Docker Compose
持久化磁盘目录
内网访问地址
防火墙限制
Qdrant API Key
备份目录
```

## 自建环境变量

```env
QDRANT_MODE=remote
QDRANT_DEPLOYMENT=self_hosted
QDRANT_URL=http://qdrant.internal:6333
QDRANT_API_KEY=公司内部QdrantKey
QDRANT_COLLECTION=digital_employee_knowledge_preprod
QDRANT_TOP_K=5
QDRANT_SCORE_THRESHOLD=0.65
```

## 部署要求

```text
1. 不要公网裸露 6333。
2. 优先只允许 FastAPI 应用服务器访问 Qdrant。
3. 必须配置 API Key。
4. 必须挂载持久化目录。
5. 必须有备份策略。
```

## 验收标准

```text
1. 应用服务器能访问自建 Qdrant。
2. 本机开发环境不能随便访问生产 Qdrant。
3. check_qdrant_self_hosted.py 通过。
4. rebuild_qdrant_collection.py 能从 MySQL 重建 collection。
5. AskGraphV2 能从自建 Qdrant 检索。
6. Qdrant Cloud 和自建 Qdrant 检索结果差异可接受。
```

------

# 六、阶段 E：Cloud 到自建 Qdrant 的迁移方案

## 推荐迁移方式

不要从 Qdrant Cloud 直接导出再导入。

你这个项目的权威数据源应该是：

```text
MySQL knowledge_card
```

Qdrant 只是向量索引，不是主数据库。

所以迁移时应该：

```text
MySQL approved + enabled + deleted=0 知识
  ↓
重新生成 embedding
  ↓
写入自建 Qdrant collection
  ↓
抽样检索验收
```

## 迁移步骤

```text
1. 停止 vector_sync_worker。
2. 锁定知识审核入口，避免迁移期间新增 approved 知识。
3. 在自建 Qdrant 创建 digital_employee_knowledge_preprod。
4. 执行 rebuild_qdrant_collection.py。
5. 抽样 20 条知识做检索验证。
6. 切换 .env 指向自建 Qdrant。
7. 重启 FastAPI 和 worker。
8. 跑 check_full_rag_flow.py。
9. 开放知识审核入口。
```

## 回滚方案

```text
1. 保留 Qdrant Cloud collection 7~14 天。
2. .env 改回 QDRANT_DEPLOYMENT=cloud。
3. 重启 FastAPI 和 worker。
4. 暂停自建 Qdrant 写入。
```

你原方案中也已经设计了 `QDRANT_READONLY=true` 这类回滚控制，适合在迁移或故障时让向量库只查不写，避免污染索引。

------

# 七、最终阶段表

| 阶段               | Qdrant 形态                  | 主要目标                         | 是否部署本地 Qdrant |
| ------------------ | ---------------------------- | -------------------------------- | ------------------- |
| 阶段 1：开发联调   | Qdrant Cloud                 | 跑通写入、检索、RAG 闭环         | 不部署              |
| 阶段 2：测试验收   | Qdrant Cloud                 | 验证知识卡片、同步任务、AskGraph | 不部署              |
| 阶段 3：预生产     | 服务器自建 Qdrant            | 模拟正式环境，做迁移演练         | 部署                |
| 阶段 4：正式上线   | 服务器自建 Qdrant            | 承接真实企微流量                 | 已部署              |
| 阶段 5：上线后观察 | 自建 Qdrant + Cloud 备份保留 | 观察稳定性，可回滚               | 已部署              |

------

# 八、你现在应该怎么改原生产 V1 方案

原来你的阶段 2 是：

```text
阶段 2：Redis + Qdrant remote 基础设施接入
```

建议拆成：

```text
阶段 2A：Redis + Qdrant Cloud 接入
阶段 2B：VectorStore 抽象层改造
阶段 2C：向量同步任务化
阶段 2D：预生产自建 Qdrant 部署与迁移
```

调整后的顺序：

```text
阶段 0：生产化基线确认与分支冻结
阶段 1：生产配置体系与环境硬校验
阶段 2A：Qdrant Cloud 开发测试接入
阶段 2B：VectorStore 抽象层改造
阶段 2C：向量同步任务化
阶段 3：DeepSeek 真实 LLM 接入
阶段 4：LangSmith 真实接入
阶段 5：AskGraphV2 问答图升级
阶段 6：企微指令路由与沉淀会话
阶段 7：KnowledgeDepositGraph 知识沉淀图
阶段 8：Redis + 企微消息去重
阶段 9：企业微信真实 AES 回调
阶段 10：服务器自建 Qdrant + 迁移演练
阶段 11：生产部署、灰度上线、回滚预案
```

这里有一个关键变化：

```text
Qdrant Cloud 接入提前。
服务器自建 Qdrant 放到真实企微上线前。
```

这样你开发阶段不用被 Docker、本地端口、持久化目录卡住，但上线前仍然能把数据控制权收回到公司服务器。

------

# 九、给 Cursor 的执行提示词

你可以直接把下面这段给 Cursor。

```text
本阶段目标：将当前项目的 Qdrant 接入方式调整为“开发测试阶段使用 Qdrant Cloud，后续生产阶段可无侵入切换到服务器自建 Qdrant”。

重要限制：
1. 本阶段不要本地部署 Qdrant。
2. 不要新增 docker-compose 里的 qdrant 服务。
3. 不要修改企业微信真实回调逻辑。
4. 不要改 DeepSeek、LangSmith、AskGraphV2 的复杂逻辑。
5. 不要在代码里写死 Qdrant Cloud URL、API Key、collection。
6. 所有配置必须从 .env 读取。
7. 所有新增代码必须加中文注释。
8. 所有新增脚本必须支持 PowerShell 环境运行。

请完成以下任务：

一、配置改造
1. 在 settings 中新增：
   - VECTOR_PROVIDER=qdrant
   - QDRANT_MODE=remote
   - QDRANT_DEPLOYMENT=cloud
   - QDRANT_URL
   - QDRANT_API_KEY
   - QDRANT_COLLECTION
   - QDRANT_TOP_K
   - QDRANT_SCORE_THRESHOLD
   - QDRANT_TIMEOUT_SECONDS
2. 更新 .env.example，增加 Qdrant Cloud 配置示例，但不要写真实 Key。
3. 启动日志中不允许打印 QDRANT_API_KEY 明文。

二、向量库抽象
1. 新增 app/rag/vector_store_base.py。
2. 新增 app/rag/qdrant_client_factory.py。
3. 新增 app/rag/qdrant_store.py。
4. 业务代码只能依赖 VectorStore 抽象，不允许直接创建 QdrantClient。

三、Qdrant Cloud 验证脚本
1. 新增 scripts/check_qdrant_cloud.py。
2. 脚本需要完成：
   - 检查 QDRANT_URL 是否存在
   - 检查 QDRANT_API_KEY 是否存在
   - 创建或确认 collection 存在
   - 写入一条测试向量
   - 使用相似问题检索
   - 输出清晰的中文验收结果
3. 脚本失败时要输出明确原因。

四、文档
1. 新增 docs/QDRANT_CLOUD_DEV_TEST_GUIDE.md。
2. 文档说明：
   - 为什么开发测试阶段使用 Qdrant Cloud
   - 如何配置 .env
   - 如何运行 check_qdrant_cloud.py
   - 哪些数据不能上传到 Cloud
   - 后续如何切换到服务器自建 Qdrant

五、验收
请最后输出：
1. 修改文件清单。
2. 新增文件清单。
3. 本阶段未做事项。
4. 验收命令。
5. Qdrant Cloud 连接测试结果。
```

