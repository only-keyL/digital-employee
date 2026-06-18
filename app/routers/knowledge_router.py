"""知识卡片 REST API 路由（/api/knowledge-cards）。"""

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.common_schema import error_response, success_response
from app.schemas.knowledge_schema import KnowledgeAuditRequest, KnowledgeCreate, KnowledgeUpdate
from app.services.knowledge_service import KnowledgeService, KnowledgeServiceError
from app.services.duplicate_check_service import DuplicateCheckError

router = APIRouter(prefix="/api/knowledge-cards", tags=["knowledge-cards"])


@router.get("")
def list_knowledge_cards(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """分页查询知识卡片列表。"""
    try:
        data = KnowledgeService(db).list_api(page=page, page_size=page_size)
        return success_response(data)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.get("/{card_id}")
def get_knowledge_card(card_id: int, db: Session = Depends(get_db)):
    """按 ID 获取知识卡片详情。"""
    try:
        data = KnowledgeService(db).get_detail(card_id)
        return success_response(data)
    except KnowledgeServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.post("")
def create_knowledge_card(payload: KnowledgeCreate, db: Session = Depends(get_db)):
    """创建知识卡片（draft 状态）。"""
    try:
        data = KnowledgeService(db).create(payload)
        return success_response(data, "创建成功")
    except KnowledgeServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.put("/{card_id}")
def update_knowledge_card(card_id: int, payload: KnowledgeUpdate, db: Session = Depends(get_db)):
    """更新知识卡片内容。"""
    try:
        data = KnowledgeService(db).update(card_id, payload)
        return success_response(data, "更新成功")
    except KnowledgeServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.post("/{card_id}/duplicate-check")
def check_duplicate_knowledge_card(card_id: int, db: Session = Depends(get_db)):
    """手动检测知识卡片是否与已有知识高度相似。"""
    try:
        data = KnowledgeService(db).check_duplicate(card_id)
        return success_response(data, "重复检测完成")
    except KnowledgeServiceError as exc:
        return error_response(exc.message)
    except DuplicateCheckError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.post("/{card_id}/audit")
def audit_knowledge_card(card_id: int, payload: KnowledgeAuditRequest, db: Session = Depends(get_db)):
    """审核知识卡片（通过/拒绝）。"""
    try:
        data = KnowledgeService(db).audit(card_id, payload)
        return success_response(data, "审核完成")
    except KnowledgeServiceError as exc:
        return error_response(exc.message)
    except ValidationError as exc:
        return error_response(str(exc.errors()[0]["msg"]))
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.post("/{card_id}/sync-vector")
def sync_knowledge_card_vector(card_id: int, db: Session = Depends(get_db)):
    """将已审核卡片同步到 Qdrant 向量库。"""
    try:
        data = KnowledgeService(db).sync_vector(card_id)
        return success_response(data, "向量同步完成")
    except KnowledgeServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.post("/{card_id}/enable")
def enable_knowledge_card(card_id: int, db: Session = Depends(get_db)):
    """启用知识卡片（参与检索）。"""
    try:
        data = KnowledgeService(db).enable(card_id)
        return success_response(data, "已启用")
    except KnowledgeServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.post("/{card_id}/disable")
def disable_knowledge_card(card_id: int, db: Session = Depends(get_db)):
    """停用知识卡片（不参与检索）。"""
    try:
        data = KnowledgeService(db).disable(card_id)
        return success_response(data, "已停用")
    except KnowledgeServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")


@router.delete("/{card_id}")
def delete_knowledge_card(card_id: int, db: Session = Depends(get_db)):
    """软删除知识卡片。"""
    try:
        KnowledgeService(db).soft_delete(card_id)
        return success_response(None, "删除成功")
    except KnowledgeServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败: {exc}")
