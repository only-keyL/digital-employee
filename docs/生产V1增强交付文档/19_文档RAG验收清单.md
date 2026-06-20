# 文档 RAG 验收清单

## 1. 环境准备

| 项 | 要求 |
| --- | --- |
| Python | 3.11+，已创建 `.venv` |
| MySQL | 已建库，`.env` 中配置 `MYSQL_*` 或 `DATABASE_URL` |
| Qdrant | 本地模式：`QDRANT_MODE=local`（默认 `./storage/qdrant`） |
| Embedding | `EMBEDDING_PROVIDER` 非 disabled；fastembed 或 openai_compatible |
| 编码 | Windows 建议 `$env:PYTHONIOENCODING="utf-8"` |

敏感配置示例（占位符，勿写真实 Key）：

```env
MYSQL_HOST=127.0.0.1
MYSQL_PASSWORD=your_password
EMBEDDING_PROVIDER=fastembed
QDRANT_MODE=local
```

## 2. 阶段1验收

```powershell
cd F:\WorkSpace\digital-employee-assistant
.\.venv\Scripts\Activate.ps1
$env:PYTHONIOENCODING="utf-8"

python scripts/prod/init_document_tables.py --env-file ".env"
python scripts/prod/check_document_stage1.py --env-file ".env"
```

**通过标准**：表存在、解析/切片服务正常、`app.main` 可 import。

## 3. 阶段2验收

```powershell
python scripts/prod/check_document_stage2_rag.py --env-file ".env" --fast
python scripts/prod/check_document_stage2_rag.py --env-file ".env"
```

| 模式 | 检查范围 |
| --- | --- |
| `--fast` | builder、repository、schema、import |
| 默认 full | 真实 Qdrant 同步 + `RetrievalService` 命中文档切片 |

## 4. 推荐补充回归

```powershell
python scripts/prod/check_rag_v2.py --env-file ".env" --question "测试问题"
python scripts/prod/run_all_regression_checks.py --env-file "docs/prod/.env" --fast
python scripts/prod/check_enhance_stage7_docs.py
```

> 若 Redis 未启动，`run_all_regression_checks.py` 中 Stage4 补充可能失败，属于**环境依赖**，不等同于文档 RAG 功能失败。

## 5. 页面验收

| 步骤 | 操作 | 预期 |
| --- | --- | --- |
| 1 | 打开 `http://127.0.0.1:8001/documents` | 列表页正常 |
| 2 | 进入 `/documents/upload`，上传 `.md` 文件 | 解析成功，`chunk_count > 0` |
| 3 | 进入文档详情 | 可见切片列表与 `section_path` |
| 4 | 点击「同步向量」 | chunk `vector_status` → `synced` |
| 5 | 重复上传同一文件 | 不重复创建记录（file_hash 去重） |

## 6. API 验收

### 上传

```powershell
curl -X POST "http://127.0.0.1:8001/api/documents/upload" `
  -F "file=@test.md" `
  -F "doc_name=测试手册" `
  -F "doc_type=manual"
```

### 同步向量

```powershell
curl -X POST "http://127.0.0.1:8001/api/documents/{doc_id}/sync-vector"
```

### 文档问答

```powershell
curl -X POST "http://127.0.0.1:8001/api/ask" `
  -H "Content-Type: application/json" `
  -d "{\"question\":\"文档里审批流程是什么\",\"user_id\":\"demo_user\",\"group_id\":\"demo_group\",\"source_type\":\"web\"}"
```

检查响应：`matched`、`sources` 含 `source_type=document_chunk` 或 `answer_source` 为 `document_chunk` / `mixed`。

## 7. 通过标准（文档知识库三阶段）

| # | 标准 |
| --- | --- |
| 1 | 文档可上传、可解析、可切片 |
| 2 | MySQL 写入 `document_source` / `document_chunk` |
| 3 | chunk 可同步 Qdrant，`vector_status=synced` |
| 4 | `/api/ask` 能命中文档切片 |
| 5 | `sources` 含文档名、章节、页码、chunk_id |
| 6 | 知识卡片问答不回归（原有验收仍 PASS） |
| 7 | 交付文档 16～19 齐全 |

## 8. 常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| PDF 解析失败 | 扫描件无可复制文本 | 换文本型 PDF 或后续 OCR 增强 |
| Qdrant 同步失败 | 本地路径无写权限或维度不一致 | 检查 `QDRANT_LOCAL_PATH`、embedding 维度 |
| Embedding 报错 | API Key / 模型未配置 | 检查 `.env` 中 `EMBEDDING_*` |
| 问答未命中文档 | 未同步向量或问题与正文语义差距大 | 先 sync-vector，用贴近正文的问题测试 |
| 回归 Redis 失败 | `127.0.0.1:6379` 未启动 | 启动 Redis 或忽略该单项 |
| 远程 Qdrant warning | `QDRANT_URL` 未配置 | 本地 `/api/ask` 仍可用，仅远程 collection 未同步 |

## 9. 一键命令汇总

```powershell
cd F:\WorkSpace\digital-employee-assistant
.\.venv\Scripts\Activate.ps1
$env:PYTHONIOENCODING="utf-8"

python scripts/prod/check_document_stage1.py --env-file ".env"
python scripts/prod/check_document_stage2_rag.py --env-file ".env" --fast
python scripts/prod/check_document_stage2_rag.py --env-file ".env"
python scripts/prod/check_enhance_stage7_docs.py
```
