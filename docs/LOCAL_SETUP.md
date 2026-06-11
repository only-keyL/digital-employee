# 本地启动说明

> 一站式本地环境准备与服务启动。MVP 默认地址：`http://127.0.0.1:8001`

## 1. 环境要求

| 项 | 要求 |
|----|------|
| Python | 3.10 或 3.11（推荐） |
| MySQL | 8.x，阶段二起必需 |
| 磁盘 | fastembed 模型约数百 MB |
| 网络 | 首次运行 fastembed 需联网下载模型 |
| OS | Windows / macOS / Linux |

---

## 2. 首次安装

```powershell
cd F:\WorkSpace\digital-employee-assistant

# 创建并激活虚拟环境（若尚未创建）
python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### 复制环境变量（仅首次执行）

```powershell
Copy-Item .env.example .env
```

> **已有 `.env` 时不要覆盖**，避免丢失已配置的 API Key。

按需编辑 `.env` 中的 `MYSQL_*`、`APP_PORT` 等。

---

## 3. .env 配置要点

| 变量 | 默认 | 说明 |
|------|------|------|
| `APP_PORT` | `8001` | 与 uvicorn `--port` 一致 |
| `LLM_PROVIDER` | `mock` | 无 Key 可演示 |
| `QDRANT_MODE` | `local` | 数据目录 `./storage/qdrant` |
| `LANGSMITH_TRACING` | `false` | 默认关闭 |
| `WECOM_ENABLED` | `false` | 企微真实回调关闭 |
| `WECOM_MOCK_ENABLED` | `true` | Mock 回调开启 |

完整项见项目根目录 `.env.example`。

---

## 4. MySQL 初始化

### 4.1 创建数据库

```powershell
mysql -u root -p < scripts/init_mysql.sql
```

或手动执行其中的 `CREATE DATABASE`。

### 4.2 建表与默认配置

```powershell
python app/db/init_db.py
```

### 4.3 验证

```powershell
python scripts/check_db.py
```

---

## 5. Seed 数据

```powershell
python scripts/seed_knowledge.py
```

幂等执行，已有卡片会跳过。

```powershell
python scripts/check_seed_data.py
```

期望：`approved + enabled` 知识卡片 ≥ 5 条。

---

## 6. Qdrant Rebuild

> **必须在 uvicorn 停止时执行**。Qdrant local 不支持多进程同时访问。

```powershell
python scripts/rebuild_qdrant.py --recreate
```

---

## 7. check_rag

仍在 **停服务状态** 下执行：

```powershell
python scripts/check_rag.py
```

通过后再启动 uvicorn。

---

## 8. 单实例 uvicorn 启动

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

验证：

- 浏览器：`http://127.0.0.1:8001`
- 健康检查：`http://127.0.0.1:8001/api/health`

```powershell
# 另一终端
python scripts/check_health.py
```

---

## 9. 端口冲突处理

若启动报 `WinError 10048` / 地址已在使用：

```powershell
netstat -ano | findstr :8001
taskkill /PID <PID> /F
```

确认仅保留一个 uvicorn 进程。

---

## 10. Qdrant local 锁说明

- 数据路径：`./storage/qdrant`（不提交 Git）
- **单实例规则**：运行中勿执行 `rebuild_qdrant.py --recreate` 或其他直接访问 Qdrant 的脚本
- 需 rebuild 时：先 `Ctrl+C` 停止 uvicorn → rebuild → check_rag → 再启动

---

## 11. 可选：DeepSeek 配置

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的Key
```

- 无 Key 或调用失败时自动降级 MockLLM
- Key 仅放 `.env`，勿提交 Git
- 修改后需重启 uvicorn

---

## 12. 可选：LangSmith 配置

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=你的Key
LANGSMITH_PROJECT=digital-employee-assistant
LANGSMITH_HIDE_INPUTS=true
LANGSMITH_HIDE_OUTPUTS=true
```

重启后：

```powershell
python scripts/check_langsmith.py
```

默认关闭模式无需 Key 即可通过验收。

---

## 13. 可选：企业微信配置

MVP 默认仅需 Mock，无需配置 Token。

真实接入（生产向，非 MVP 必做）见 [`WECOM_INTEGRATION.md`](WECOM_INTEGRATION.md)。

```env
WECOM_ENABLED=true
WECOM_TOKEN=...
WECOM_ENCODING_AES_KEY=...
```

Mock 验收（无需上述配置）：

```powershell
python scripts/check_wecom_mock.py
```

---

## 14. 停止和重置流程

### 日常停止

在 uvicorn 终端 `Ctrl+C`。

### 重置向量库（完整刷新）

```powershell
# 1. 停止 uvicorn
# 2. 重新导入种子（可选）
python scripts/seed_knowledge.py
# 3. 重建 Qdrant
python scripts/rebuild_qdrant.py --recreate
python scripts/check_rag.py
# 4. 重启 uvicorn
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

### MVP 全量验收

见 [`ACCEPTANCE_CHECKLIST.md`](ACCEPTANCE_CHECKLIST.md#mvp-最终验收)。

---

## 相关文档

- [MVP_DELIVERY.md](MVP_DELIVERY.md) — 交付总览
- [DEMO_SCRIPT.md](DEMO_SCRIPT.md) — 演示脚本
- [ACCEPTANCE_CHECKLIST.md](ACCEPTANCE_CHECKLIST.md) — 验收清单
