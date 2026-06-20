"""文档知识库 REST API 路由（/api/documents）。"""

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.common_schema import error_response, success_response
from app.schemas.document_schema import DocTypeInput, DocumentUploadMeta
from app.services.document_service import DocumentService, DocumentServiceError
from app.services.document_vector_sync_service import DocumentVectorSyncService

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    doc_name: str = Form(...),
    doc_type: DocTypeInput = Form("other"),
    system_name: str | None = Form(None),
    module_name: str | None = Form(None),
    version: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """上传文档并触发解析切片。"""
    try:
        meta = DocumentUploadMeta(
            doc_name=doc_name,
            doc_type=doc_type,
            system_name=system_name,
            module_name=module_name,
            version=version,
        )
        data = await DocumentService(db).upload(file, meta)
        return success_response(data, "上传成功")
    except DocumentServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.get("")
def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """分页查询文档列表。"""
    try:
        data = DocumentService(db).list_api(page=page, page_size=page_size)
        return success_response(data)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.get("/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db)):
    """获取文档详情。"""
    try:
        data = DocumentService(db).get_detail(doc_id)
        return success_response(data)
    except DocumentServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.get("/{doc_id}/chunks")
def list_document_chunks(
    doc_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """获取文档切片列表。"""
    try:
        data = DocumentService(db).list_chunks(doc_id, page=page, page_size=page_size)
        return success_response(data)
    except DocumentServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.post("/{doc_id}/reparse")
def reparse_document(doc_id: int, db: Session = Depends(get_db)):
    """重新解析并切片（旧 chunk 逻辑删除）。"""
    try:
        data = DocumentService(db).reparse(doc_id)
        return success_response(data, "重新解析完成")
    except DocumentServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.post("/{doc_id}/enable")
def enable_document(doc_id: int, db: Session = Depends(get_db)):
    """启用文档。"""
    try:
        data = DocumentService(db).enable(doc_id)
        return success_response(data, "已启用")
    except DocumentServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.post("/{doc_id}/disable")
def disable_document(doc_id: int, db: Session = Depends(get_db)):
    """禁用文档。"""
    try:
        data = DocumentService(db).disable(doc_id)
        return success_response(data, "已禁用")
    except DocumentServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.delete("/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    """逻辑删除文档及其切片。"""
    try:
        data = DocumentService(db).delete(doc_id)
        return success_response(data, "已删除")
    except DocumentServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.post("/{doc_id}/sync-vector")
def sync_document_vectors(doc_id: int, db: Session = Depends(get_db)):
    """同步单篇文档的全部切片向量到 Qdrant。"""
    try:
        stats = DocumentVectorSyncService(db).sync_document(doc_id)
        return success_response(stats, "向量同步完成")
    except ValueError as exc:
        return error_response(str(exc))
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.post("/{doc_id}/delete-vector")
def delete_document_vectors(doc_id: int, db: Session = Depends(get_db)):
    """删除单篇文档在 Qdrant 中的向量。"""
    try:
        stats = DocumentVectorSyncService(db).delete_document_vectors(doc_id)
        return success_response(stats, "向量已删除")
    except ValueError as exc:
        return error_response(str(exc))
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.post("/rebuild-vector")
def rebuild_document_vectors(
    recreate: bool = Query(False),
    db: Session = Depends(get_db),
):
    """重建全部文档切片向量索引。"""
    try:
        stats = DocumentVectorSyncService(db).rebuild_all_documents(recreate=recreate)
        return success_response(stats, "重建完成")
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.post("/chunks/{chunk_id}/sync-vector")
def sync_document_chunk_vector(chunk_id: int, db: Session = Depends(get_db)):
    """同步单个文档切片向量。"""
    try:
        chunk = DocumentVectorSyncService(db).sync_chunk(chunk_id)
        return success_response(
            {
                "chunk_id": chunk.id,
                "vector_status": chunk.vector_status,
                "vector_id": chunk.vector_id,
                "vector_error": chunk.vector_error,
            },
            "切片向量同步完成",
        )
    except ValueError as exc:
        return error_response(str(exc))
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")
