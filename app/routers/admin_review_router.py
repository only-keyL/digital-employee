"""后台审核 REST API（阶段 5/6）：Token 鉴权 + 操作审计查询。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.admin_auth import require_admin_auth
from app.db.database import get_db
from app.schemas.admin_review_schema import ContributionMarkReviewRequest, KnowledgeReviewActionRequest
from app.schemas.common_schema import error_response, success_response
from app.services.admin_operation_log_service import AdminOperationLogService
from app.services.admin_review_service import AdminReviewService, AdminReviewServiceError

router = APIRouter(
    prefix="/api/admin",
    tags=["admin-review"],
    dependencies=[Depends(require_admin_auth)],
)


def _parse_duplicate_filter(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes"}:
        return True
    if lowered in {"0", "false", "no"}:
        return False
    return None


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    """提取审计所需的客户端 IP 与 User-Agent（不记录 Token）。"""
    forwarded = request.headers.get("x-forwarded-for")
    ip = (forwarded.split(",")[0].strip() if forwarded else None) or (
        request.client.host if request.client else None
    )
    return ip, request.headers.get("user-agent")


@router.get("/contributions")
def list_contributions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    risk_level: str | None = Query(None),
    duplicate_suspected: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """分页查询知识投稿列表（不含完整 raw_content）。"""
    try:
        data = AdminReviewService(db).list_contributions(
            page=page,
            page_size=page_size,
            status=status,
            risk_level=risk_level,
            duplicate_suspected=_parse_duplicate_filter(duplicate_suspected),
        )
        return success_response(data, "查询成功")
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败：{exc}")


@router.get("/contributions/{contribution_id}")
def get_contribution_detail(contribution_id: str, db: Session = Depends(get_db)):
    """查询投稿详情（脱敏预览，不含完整正文）。"""
    try:
        detail = AdminReviewService(db).get_contribution_detail(contribution_id)
        return success_response(detail.model_dump(), "查询成功")
    except AdminReviewServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败：{exc}")


@router.get("/knowledge/pending")
def list_pending_knowledge(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """分页查询 audit_status=pending 的知识卡片。"""
    try:
        data = AdminReviewService(db).list_pending_knowledge(page=page, page_size=page_size)
        return success_response(data, "查询成功")
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败：{exc}")


@router.get("/knowledge/{knowledge_id}")
def get_pending_knowledge_detail(knowledge_id: int, db: Session = Depends(get_db)):
    """查询待审核知识详情（供审核人查看完整字段）。"""
    try:
        detail = AdminReviewService(db).get_pending_knowledge_detail(knowledge_id)
        return success_response(detail.model_dump(), "查询成功")
    except AdminReviewServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败：{exc}")


@router.post("/knowledge/{knowledge_id}/approve")
def approve_knowledge(
    request: Request,
    knowledge_id: int,
    payload: KnowledgeReviewActionRequest,
    db: Session = Depends(get_db),
):
    """审核通过 pending 知识：启用并入队 vector_sync_task，不阻塞等待 Qdrant。"""
    ip, ua = _client_meta(request)
    try:
        req = payload.model_copy(update={"action": "approve"})
        data = AdminReviewService(db).approve_knowledge(
            knowledge_id,
            req,
            ip_address=ip,
            user_agent=ua,
        )
        return success_response(data, data.get("message", "审核通过"))
    except ValidationError as exc:
        return error_response(f"参数校验失败：{exc.errors()[0]['msg']}")
    except AdminReviewServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败：{exc}")


@router.post("/knowledge/{knowledge_id}/reject")
def reject_knowledge(
    request: Request,
    knowledge_id: int,
    payload: KnowledgeReviewActionRequest,
    db: Session = Depends(get_db),
):
    """审核拒绝 pending 知识：必须填写 audit_remark，不创建 vector_sync_task。"""
    ip, ua = _client_meta(request)
    try:
        req = payload.model_copy(update={"action": "reject"})
        data = AdminReviewService(db).reject_knowledge(
            knowledge_id,
            req,
            ip_address=ip,
            user_agent=ua,
        )
        return success_response(data, data.get("message", "审核已拒绝"))
    except ValidationError as exc:
        return error_response(f"参数校验失败：{exc.errors()[0]['msg']}")
    except AdminReviewServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败：{exc}")


@router.post("/contributions/{contribution_id}/mark-reviewed")
def mark_contribution_reviewed(
    request: Request,
    contribution_id: str,
    payload: ContributionMarkReviewRequest,
    db: Session = Depends(get_db),
):
    """人工标记 duplicate_suspected / risk_blocked 投稿，不修改 knowledge_card 审核状态。"""
    ip, ua = _client_meta(request)
    try:
        data = AdminReviewService(db).mark_contribution_reviewed(
            contribution_id,
            payload,
            ip_address=ip,
            user_agent=ua,
        )
        return success_response(data, data.get("message", "标记成功"))
    except ValidationError as exc:
        return error_response(f"参数校验失败：{exc.errors()[0]['msg']}")
    except AdminReviewServiceError as exc:
        return error_response(exc.message)
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败：{exc}")


@router.get("/operation-logs")
def list_operation_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    operator: str | None = Query(None),
    action: str | None = Query(None),
    target_type: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """分页查询后台操作审计日志。"""
    try:
        data = AdminOperationLogService(db).list_logs(
            page=page,
            page_size=page_size,
            operator=operator,
            action=action,
            target_type=target_type,
        )
        return success_response(data, "查询成功")
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败：{exc}")


@router.get("/operation-logs/{operation_id}")
def get_operation_log_detail(operation_id: str, db: Session = Depends(get_db)):
    """查询单条操作审计详情。"""
    try:
        detail = AdminOperationLogService(db).get_detail(operation_id)
        if detail is None:
            return error_response("审计记录不存在")
        return success_response(detail, "查询成功")
    except SQLAlchemyError as exc:
        return error_response(f"数据库操作失败：{exc}")
