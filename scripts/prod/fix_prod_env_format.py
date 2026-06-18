"""一次性修复 docs/prod/.env 格式（本地运行，不输出真实值）。"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

ENV_PATH = Path("docs/prod/.env")


def _quote_if_needed(value: str) -> str:
    v = value.strip().strip('"').strip("'")
    if any(c in v for c in '# $&=:\\"\' ') or v.startswith("redis://"):
        escaped = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return v


def fix_env_file() -> list[str]:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    kv: dict[str, str] = {}
    notes: list[str] = []

    for i, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            notes.append(f"L{i}: 无等号行已忽略（建议改为注释）")
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()

        # 键名规范化映射
        key_map = {
            "deepseek": "LLM_API_KEY",
            "APIkey": "QDRANT_API_KEY",
            "Cluster Endpoint": "QDRANT_URL",
        }
        norm_key = key_map.get(key, key)
        if norm_key != key:
            notes.append(f"L{i}: 键名 {key!r} -> {norm_key}")
        kv[norm_key] = val

    # 从拆分 Redis 字段构建 REDIS_URL
    if "REDIS_URL" not in kv and "REDIS_HOST" in kv:
        host = kv.get("REDIS_HOST", "").strip('"')
        port = kv.get("REDIS_PORT", "6379").strip('"')
        password = kv.get("REDIS_PASSWORD", "").strip('"')
        account = kv.get("REDIS_ACCOUNT", "").strip('"')
        if password:
            user_part = f"{account}:" if account else ""
            redis_url = f"redis://{user_part}{quote(password, safe='')}@{host}:{port}/0"
        else:
            redis_url = f"redis://{host}:{port}/0"
        kv["REDIS_URL"] = redis_url
        notes.append("已根据 REDIS_* 字段构建 REDIS_URL")

    # 补全阶段 2 必需字段默认值（不覆盖已有值）
    defaults = {
        "APP_ENV": "dev",
        "LLM_PROVIDER": "deepseek",
        "QDRANT_MODE": "remote",
        "LLM_BASE_URL": "https://api.deepseek.com",
        "LLM_MODEL": "deepseek-v4-flash",
    }
    for k, v in defaults.items():
        if k not in kv and k == "LLM_PROVIDER" and "LLM_API_KEY" in kv:
            kv[k] = v
            notes.append(f"补充默认 {k}")
        elif k not in kv and k != "LLM_PROVIDER":
            if k == "APP_ENV" and "APP_ENV" not in kv:
                kv[k] = v
            elif k in ("QDRANT_MODE",) and "QDRANT_URL" in kv:
                kv[k] = v
                notes.append(f"补充默认 {k}")

    if "LLM_API_KEY" in kv and "LLM_PROVIDER" not in kv:
        kv["LLM_PROVIDER"] = "deepseek"
        notes.append("补充 LLM_PROVIDER=deepseek")

    if "QDRANT_URL" in kv and "QDRANT_MODE" not in kv:
        kv["QDRANT_MODE"] = "remote"
        notes.append("补充 QDRANT_MODE=remote")

    if "QDRANT_URL" in kv and "QDRANT_COLLECTION" not in kv:
        kv["QDRANT_COLLECTION"] = "digital_employee_knowledge_dev"

    # 重写文件（保留头部注释块）
    header: list[str] = []
    for raw in lines:
        if raw.strip().startswith("#") or not raw.strip():
            header.append(raw)
        else:
            break

    ordered_keys = [
        "APP_ENV",
        "LANGSMITH_TRACING",
        "LANGSMITH_API_KEY",
        "LANGSMITH_PROJECT",
        "LANGSMITH_ENDPOINT",
        "LLM_PROVIDER",
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "QDRANT_MODE",
        "QDRANT_URL",
        "QDRANT_API_KEY",
        "QDRANT_COLLECTION",
        "REDIS_URL",
        "REDIS_HOST",
        "REDIS_PORT",
        "REDIS_PASSWORD",
        "REDIS_ACCOUNT",
    ]

    out: list[str] = list(header) if header else ["# docs/prod/.env — 生产真实配置（禁止提交 Git）"]
    if out and out[-1].strip():
        out.append("")

    written = set()
    for key in ordered_keys:
        if key in kv:
            out.append(f"{key}={_quote_if_needed(kv[key])}")
            written.add(key)

    for key, val in sorted(kv.items()):
        if key not in written:
            out.append(f"{key}={_quote_if_needed(val)}")

    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
    return notes


if __name__ == "__main__":
    changes = fix_env_file()
    print("修复完成，变更摘要：")
    for item in changes:
        print(f"  - {item}")
