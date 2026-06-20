#!/usr/bin/env python
"""文档知识库阶段1验收脚本。

检查表结构、Repository 基础能力、解析/切片服务与 app.main 可导入性。
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import inspect

from app.core.settings import apply_env_file
from app.db.database import SessionLocal, engine
from app.models.document_chunk import DocumentChunk
from app.models.document_source import DocumentSource
from app.repositories.document_repository import DocumentRepository
from app.services.document_chunk_service import DocumentChunkService
from app.services.document_parse_service import DocumentParseService

DEFAULT_ENV_FILE = ".env"

MARKDOWN_SAMPLE = """# 合同变更

## 审批流程

提交变更申请后，系统会自动进入审批流。

## 注意事项

请确认合同编号无误。
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="文档知识库阶段1 验收")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE, help="可选环境变量文件路径")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.env_file:
        apply_env_file(args.env_file)

    failed_items: list[str] = []
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    print("=" * 60)
    print("文档知识库阶段1 验收")
    print("=" * 60)

    for table_name in ("document_source", "document_chunk"):
        if table_name in table_names:
            print(f"[PASS] 表 {table_name} 存在")
        else:
            failed_items.append(f"缺少表 {table_name}")
            print(f"[FAIL] 表 {table_name} 不存在")

    with SessionLocal() as session:
        repo = DocumentRepository(session)
        suffix = uuid.uuid4().hex[:8]
        file_hash = f"stage1-test-hash-{suffix}"

        existing = repo.get_by_file_hash(file_hash)
        if existing is not None:
            failed_items.append("测试前 file_hash 不应已存在")
            print("[FAIL] 测试 file_hash 预检异常")
        else:
            print("[PASS] file_hash 预检通过")

        doc = DocumentSource(
            doc_name=f"阶段1验收文档-{suffix}",
            doc_type="manual",
            file_name=f"sample-{suffix}.md",
            file_ext="md",
            file_size=128,
            file_hash=file_hash,
            storage_path=f"data/uploads/documents/test-{suffix}.md",
            system_name="合同管理系统",
            module_name="合同变更",
            version="v1.0",
            parse_status="parsed",
            chunk_count=2,
            enabled=1,
            deleted=0,
        )
        repo.add(doc)
        session.flush()

        chunks = [
            DocumentChunk(
                doc_id=doc.id,
                doc_name=doc.doc_name,
                chunk_index=1,
                section_title="审批流程",
                section_path="合同变更 / 审批流程",
                page_no=None,
                content="测试切片正文 1",
                content_hash=f"chunk-hash-1-{suffix}",
                token_estimate=10,
                vector_status="pending",
                enabled=1,
                deleted=0,
            ),
            DocumentChunk(
                doc_id=doc.id,
                doc_name=doc.doc_name,
                chunk_index=2,
                section_title="注意事项",
                section_path="合同变更 / 注意事项",
                page_no=None,
                content="测试切片正文 2",
                content_hash=f"chunk-hash-2-{suffix}",
                token_estimate=10,
                vector_status="pending",
                enabled=1,
                deleted=0,
            ),
        ]
        repo.add_chunks(chunks)
        session.commit()
        print("[PASS] 测试文档与多个 chunk 插入成功")

        duplicate = repo.get_by_file_hash(file_hash)
        if duplicate is None or duplicate.id != doc.id:
            failed_items.append("file_hash 查重失败")
            print("[FAIL] file_hash 查重查询异常")
        else:
            print("[PASS] file_hash 查重查询正常")

        chunk_list = repo.list_chunks_by_doc_id(doc.id)
        if len(chunk_list) < 2:
            failed_items.append("chunk 列表数量不足")
            print("[FAIL] chunk 列表查询异常")
        else:
            print("[PASS] chunk 列表查询正常")

        for chunk in chunk_list:
            if chunk.vector_status != "pending":
                failed_items.append("vector_status 应为 pending")
                print(f"[FAIL] chunk {chunk.id} vector_status={chunk.vector_status}")
                break
        else:
            print("[PASS] vector_status 均为 pending")

        dup_check = repo.get_by_file_hash(file_hash)
        if dup_check is None:
            failed_items.append("file_hash 去重查询失败")
            print("[FAIL] 重复 file_hash 查重失败")
        else:
            print("[PASS] 重复 file_hash 不会重复创建（Repository 可命中已有记录）")

        doc_id = doc.id
        for chunk in repo.list_chunks_by_doc_id(doc_id, include_deleted=True):
            session.delete(chunk)
        stored_doc = repo.get_by_id(doc_id)
        if stored_doc is not None:
            session.delete(stored_doc)
        session.commit()

    parse_service = DocumentParseService()
    segments = parse_service.parse_text(MARKDOWN_SAMPLE, "md")
    if not segments:
        failed_items.append("Markdown 解析结果为空")
        print("[FAIL] DocumentParseService Markdown 解析失败")
    else:
        print(f"[PASS] DocumentParseService Markdown 解析成功，片段数={len(segments)}")

    chunk_service = DocumentChunkService()
    drafts = chunk_service.build_chunks(
        segments,
        doc_name="合同操作手册",
        system_name="合同管理系统",
        module_name="合同变更",
    )
    if not drafts:
        failed_items.append("切片结果为空")
        print("[FAIL] DocumentChunkService 切片失败")
    elif not any(draft.section_path for draft in drafts):
        failed_items.append("切片缺少 section_path")
        print("[FAIL] DocumentChunkService 未生成 section_path")
    else:
        print(f"[PASS] DocumentChunkService 切片成功，chunk 数={len(drafts)}")

    try:
        import app.main  # noqa: F401

        print("[PASS] app.main 可正常 import")
    except Exception as exc:
        failed_items.append(f"app.main import 失败: {exc}")
        print(f"[FAIL] app.main import 失败: {exc}")

    print("=" * 60)
    if failed_items:
        print(f"[FAIL] 文档知识库阶段1 验收未通过，共 {len(failed_items)} 项")
        for item in failed_items:
            print(f"  - {item}")
        return 1

    print("[PASS] 文档知识库阶段1 验收全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
