#!/usr/bin/env python
"""Stage3 RAG 链路验收脚本（脱敏输出）。"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.desensitize import sanitize_text
from app.core.settings import Settings, apply_env_file
from app.db.database import SessionLocal
from app.graphs.ask_graph_v2 import AskGraphV2Runner
from app.rag.qdrant_vector_store import get_qdrant_vector_store

DEFAULT_ENV_FILE = "docs/prod/.env"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage3 RAG 验收")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    parser.add_argument("--question", required=True, help="测试问题")
    return parser.parse_args()


def check_embedding(settings: Settings) -> tuple[bool, str]:
    provider = (settings.embedding_provider or "").strip().lower()
    if provider in {"", "disabled", "mock"}:
        return False, "EMBEDDING_PROVIDER 未配置或为 disabled/mock"
    if provider == "openai_compatible":
        if not settings.embedding_api_key or not settings.embedding_model:
            return False, "openai_compatible 缺少 EMBEDDING_API_KEY 或 EMBEDDING_MODEL"
    elif provider in {"fastembed", "qdrant_fastembed"}:
        if not settings.embedding_model:
            return False, "fastembed 缺少 EMBEDDING_MODEL"
    if not settings.embedding_dimension:
        return False, "缺少 EMBEDDING_VECTOR_SIZE / EMBEDDING_DIMENSION"
    return True, f"provider={provider} model={settings.embedding_model}"


def check_qdrant(settings: Settings) -> tuple[bool, str]:
    try:
        store = get_qdrant_vector_store()
        store.ensure_collection(settings.embedding_dimension)
        return True, f"collection={settings.effective_qdrant_rag_collection}"
    except Exception as exc:
        return False, str(exc)


async def run_ask(question: str) -> dict:
    with SessionLocal() as session:
        runner = AskGraphV2Runner(session)
        state = await runner.run(question=question, user_id="check-rag-v2", source="check_rag_v2")
        return {
            "run_id": state.get("run_id"),
            "status": state.get("status"),
            "confidence_level": state.get("confidence_level"),
            "top_score": state.get("top_score"),
            "answer_preview": sanitize_text(state.get("answer") or "", max_length=120),
            "fallback_reason": state.get("fallback_reason"),
        }


def main() -> int:
    args = parse_args()
    env_path = Path(args.env_file)
    if not env_path.is_file():
        print(f"[FAIL] 配置文件不存在：{env_path}")
        return 2

    settings = apply_env_file(str(env_path))
    print("Stage3 RAG 验收开始")
    print(f"问题预览：{sanitize_text(args.question, max_length=80)}")

    ok, msg = check_embedding(settings)
    if not ok:
        print(f"[FAIL] Embedding 配置不可用：{msg}")
        return 1
    print(f"[OK] Embedding 配置：{msg}")

    ok, msg = check_qdrant(settings)
    if not ok:
        print(f"[FAIL] Qdrant 检查失败：{msg}")
        return 1
    print(f"[OK] Qdrant：{msg}")

    result = asyncio.run(run_ask(args.question))
    print("AskGraphV2 执行结果（脱敏）：")
    print(f"  run_id={result['run_id']}")
    print(f"  status={result['status']}")
    print(f"  confidence_level={result['confidence_level']}")
    print(f"  top_score={result['top_score']}")
    print(f"  answer_preview={result['answer_preview']}")
    print(f"  fallback_reason={result['fallback_reason']}")

    if result["status"] == "failed":
        print("[FAIL] 问答执行失败")
        return 1
    print("[PASS] RAG 验收脚本执行完成")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] RAG 验收异常：{exc}")
        raise SystemExit(1) from exc
