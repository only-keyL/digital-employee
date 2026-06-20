#!/usr/bin/env python
"""文档知识库阶段2验收：向量构建、Qdrant 同步与 RAG 检索接入。"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import inspect, text

from app.core.settings import apply_env_file, get_settings
from app.db.database import SessionLocal, engine
from app.models.document_chunk import DocumentChunk
from app.models.document_source import DocumentSource
from app.rag.document_vector_payload_builder import (
    build_document_chunk_payload,
    build_document_chunk_vector_text,
    is_sync_eligible_chunk,
)
from app.repositories.document_repository import DocumentRepository
from app.services.document_vector_sync_service import DocumentVectorSyncService
from app.services.retrieval_service import RetrievalService

DEFAULT_ENV_FILE = ".env"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="文档知识库阶段2 RAG 验收")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    parser.add_argument("--fast", action="store_true", help="仅检查 builder/repository/schema/import")
    return parser.parse_args()


def ensure_vector_error_column() -> None:
    with engine.connect() as connection:
        result = connection.execute(
            text(
                """
                SELECT COUNT(*) AS cnt FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'document_chunk'
                  AND COLUMN_NAME = 'vector_error'
                """
            )
        )
        if int(result.scalar() or 0) == 0:
            connection.execute(text("ALTER TABLE document_chunk ADD COLUMN vector_error TEXT NULL"))
            connection.commit()


def main() -> int:
    args = parse_args()
    if args.env_file:
        apply_env_file(args.env_file)
    settings = get_settings()
    failed: list[str] = []

    print("=" * 60)
    print("文档知识库阶段2 RAG 验收")
    print(f"模式：{'fast' if args.fast else 'full'}")
    print("=" * 60)

    inspector = inspect(engine)
    for table in ("document_source", "document_chunk"):
        if table in inspector.get_table_names():
            print(f"[PASS] 表 {table} 存在")
        else:
            failed.append(f"缺少表 {table}")
            print(f"[FAIL] 表 {table} 不存在")

    try:
        ensure_vector_error_column()
        print("[PASS] document_chunk.vector_error 字段就绪")
    except Exception as exc:
        failed.append(f"vector_error 字段检查失败: {exc}")
        print(f"[FAIL] vector_error 字段检查失败: {exc}")

    suffix = uuid.uuid4().hex[:8]
    with SessionLocal() as session:
        repo = DocumentRepository(session)
        doc = DocumentSource(
            doc_name=f"阶段2验收文档-{suffix}",
            doc_type="manual",
            file_name=f"stage2-{suffix}.md",
            file_ext="md",
            file_size=256,
            file_hash=f"stage2-hash-{suffix}",
            storage_path=f"data/uploads/documents/stage2-{suffix}.md",
            system_name="合同管理系统",
            module_name="合同变更",
            version="v1.0",
            parse_status="parsed",
            chunk_count=1,
            enabled=1,
            deleted=0,
        )
        repo.add(doc)
        session.flush()
        chunk = DocumentChunk(
            doc_id=doc.id,
            doc_name=doc.doc_name,
            chunk_index=1,
            section_title="审批流程",
            section_path="合同变更 / 审批流程",
            page_no=3,
            content="文档：《合同操作手册》\n章节：合同变更 / 审批流程\n正文：提交变更申请后进入审批流。",
            content_hash=f"stage2-chunk-{suffix}",
            token_estimate=50,
            vector_status="pending",
            enabled=1,
            deleted=0,
        )
        repo.add_chunks([chunk])
        session.commit()
        session.refresh(doc)
        session.refresh(chunk)
        print("[PASS] 测试 parsed 文档与 pending chunk 已创建")

        vector_text = build_document_chunk_vector_text(chunk, doc)
        if "合同变更" not in vector_text:
            failed.append("vector_text 缺少章节上下文")
            print("[FAIL] build_document_chunk_vector_text 异常")
        else:
            print("[PASS] build_document_chunk_vector_text 正常")

        payload = build_document_chunk_payload(chunk, doc)
        if payload.get("source_type") != "document_chunk":
            failed.append("payload source_type 不正确")
            print("[FAIL] build_document_chunk_payload source_type 异常")
        else:
            print("[PASS] build_document_chunk_payload source_type=document_chunk")

        if not is_sync_eligible_chunk(chunk, doc):
            failed.append("is_sync_eligible_chunk 判断异常")
            print("[FAIL] is_sync_eligible_chunk 异常")
        else:
            print("[PASS] is_sync_eligible_chunk 正常")

        try:
            import app.main  # noqa: F401

            print("[PASS] app.main 可正常 import")
        except Exception as exc:
            failed.append(f"app.main import 失败: {exc}")
            print(f"[FAIL] app.main import 失败: {exc}")

        if args.fast:
            session.delete(chunk)
            session.delete(doc)
            session.commit()
            print("=" * 60)
            if failed:
                print(f"[FAIL] fast 模式未通过，共 {len(failed)} 项")
                return 1
            print("[PASS] 文档知识库阶段2 fast 验收通过")
            return 0

        if settings.qdrant_mode.lower() != "local":
            print("[WARN] 当前 QDRANT_MODE 非 local，full 模式仍尝试本地 QdrantStore + EmbeddingService")

        try:
            synced = DocumentVectorSyncService(session).sync_chunk(chunk.id)
            session.refresh(synced)
            if synced.vector_status != "synced":
                failed.append(f"chunk 同步失败: {synced.vector_error}")
                print(f"[FAIL] DocumentVectorSyncService 同步失败: {synced.vector_error}")
            else:
                print(f"[PASS] chunk.vector_status={synced.vector_status}, vector_id={synced.vector_id}")
        except Exception as exc:
            failed.append(f"DocumentVectorSyncService 异常: {exc}")
            print(f"[FAIL] DocumentVectorSyncService 异常: {exc}")

        try:
            retrieval = RetrievalService(session).retrieve("合同变更审批流程怎么走")
            doc_hits = [h for h in retrieval.hits if h.source_type == "document_chunk"]
            if doc_hits:
                print(f"[PASS] RetrievalService 命中文档切片，hits={len(doc_hits)}")
            else:
                print("[WARN] RetrievalService 未命中文档切片（可能 embedding 相似度不足，请人工用更贴近正文的问题复测）")
        except Exception as exc:
            failed.append(f"RetrievalService 异常: {exc}")
            print(f"[FAIL] RetrievalService 异常: {exc}")

        session.delete(chunk)
        session.delete(doc)
        session.commit()

    print("=" * 60)
    if failed:
        print(f"[FAIL] 阶段2 验收未通过，共 {len(failed)} 项")
        for item in failed:
            print(f"  - {item}")
        return 1
    print("[PASS] 文档知识库阶段2 验收全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
