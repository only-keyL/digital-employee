"""后台审核 HTML 页面路由（阶段 5）。生产环境必须接鉴权。"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.db.database import get_db
from app.schemas.admin_review_schema import ContributionMarkReviewRequest, KnowledgeReviewActionRequest
from app.services.admin_review_service import AdminReviewService, AdminReviewServiceError

router = APIRouter(tags=["admin-pages"])
templates = Jinja2Templates(directory="app/templates")

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


def _page_context(request: Request, active_page: str, **extra) -> dict:
    return {
        "request": request,
        "app_name": settings.app_name,
        "app_env": settings.app_env,
        "llm_provider": settings.llm_provider,
        "embedding_provider": settings.embedding_provider,
        "langsmith_enabled": settings.is_langsmith_enabled,
        "wecom_enabled": settings.is_wecom_enabled,
        "wecom_mock_enabled": settings.wecom_mock_enabled,
        "mock_mode": settings.mock_mode,
        "active_page": active_page,
        "flash_message": request.query_params.get("msg"),
        "flash_error": request.query_params.get("error"),
        **extra,
    }


def _redirect(path: str, message: str | None = None, error: str | None = None) -> RedirectResponse:
    url = path
    params: list[str] = []
    if message:
        params.append(f"msg={quote(message)}")
    if error:
        params.append(f"error={quote(error)}")
    if params:
        url = f"{url}?{'&'.join(params)}"
    return RedirectResponse(url=url, status_code=303)


def _normalize_page(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    return page, page_size


@router.get("/admin/contributions", response_class=HTMLResponse)
def admin_contribution_list(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    status: str | None = Query(None),
    risk_level: str | None = Query(None),
    duplicate_suspected: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """知识投稿列表页。"""
    page, page_size = _normalize_page(page, page_size)
    dup_filter = None
    if duplicate_suspected:
        dup_filter = duplicate_suspected.strip().lower() in {"1", "true", "yes"}
    try:
        data = AdminReviewService(db).list_contributions(
            page=page,
            page_size=page_size,
            status=status or None,
            risk_level=risk_level or None,
            duplicate_suspected=dup_filter,
        )
        ctx = _page_context(
            request,
            "admin_contributions",
            items=data["items"],
            total=data["total"],
            page=page,
            page_size=page_size,
            status_filter=status or "",
            risk_level_filter=risk_level or "",
            duplicate_filter=duplicate_suspected or "",
        )
        return templates.TemplateResponse(
            request=request,
            name="admin/contribution_list.html",
            context=ctx,
        )
    except SQLAlchemyError as exc:
        ctx = _page_context(request, "admin_contributions", items=[], total=0, db_error=str(exc))
        return templates.TemplateResponse(
            request=request,
            name="admin/contribution_list.html",
            context=ctx,
        )


@router.get("/admin/contributions/{contribution_id}", response_class=HTMLResponse)
def admin_contribution_detail(request: Request, contribution_id: str, db: Session = Depends(get_db)):
    """知识投稿详情页。"""
    try:
        detail = AdminReviewService(db).get_contribution_detail(contribution_id)
        ctx = _page_context(request, "admin_contributions", detail=detail.model_dump())
        return templates.TemplateResponse(
            request=request,
            name="admin/contribution_detail.html",
            context=ctx,
        )
    except AdminReviewServiceError as exc:
        return _redirect("/admin/contributions", error=exc.message)
    except SQLAlchemyError as exc:
        return _redirect("/admin/contributions", error=f"数据库错误：{exc}")


@router.post("/admin/contributions/{contribution_id}/mark-reviewed")
def admin_mark_contribution_reviewed(
    contribution_id: str,
    action: str = Form(...),
    reviewer: str = Form(...),
    remark: str = Form(""),
    db: Session = Depends(get_db),
):
    try:
        payload = ContributionMarkReviewRequest(action=action, reviewer=reviewer, remark=remark or None)
        result = AdminReviewService(db).mark_contribution_reviewed(contribution_id, payload)
        return _redirect(f"/admin/contributions/{contribution_id}", message=result["message"])
    except (AdminReviewServiceError, ValidationError) as exc:
        msg = exc.message if isinstance(exc, AdminReviewServiceError) else str(exc)
        return _redirect(f"/admin/contributions/{contribution_id}", error=msg)


@router.get("/admin/knowledge/pending", response_class=HTMLResponse)
def admin_pending_knowledge_list(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """待审核知识列表页。"""
    page, page_size = _normalize_page(page, page_size)
    try:
        data = AdminReviewService(db).list_pending_knowledge(page=page, page_size=page_size)
        ctx = _page_context(
            request,
            "admin_pending_knowledge",
            items=data["items"],
            total=data["total"],
            page=page,
            page_size=page_size,
        )
        return templates.TemplateResponse(
            request=request,
            name="admin/pending_knowledge_list.html",
            context=ctx,
        )
    except SQLAlchemyError as exc:
        ctx = _page_context(request, "admin_pending_knowledge", items=[], total=0, db_error=str(exc))
        return templates.TemplateResponse(
            request=request,
            name="admin/pending_knowledge_list.html",
            context=ctx,
        )


@router.get("/admin/knowledge/{knowledge_id}", response_class=HTMLResponse)
def admin_pending_knowledge_detail(request: Request, knowledge_id: int, db: Session = Depends(get_db)):
    """待审核知识详情与审核操作页。"""
    try:
        detail = AdminReviewService(db).get_pending_knowledge_detail(knowledge_id)
        ctx = _page_context(request, "admin_pending_knowledge", detail=detail.model_dump())
        return templates.TemplateResponse(
            request=request,
            name="admin/pending_knowledge_detail.html",
            context=ctx,
        )
    except AdminReviewServiceError as exc:
        return _redirect("/admin/knowledge/pending", error=exc.message)
    except SQLAlchemyError as exc:
        return _redirect("/admin/knowledge/pending", error=f"数据库错误：{exc}")


@router.post("/admin/knowledge/{knowledge_id}/approve")
def admin_approve_knowledge(
    knowledge_id: int,
    audit_user: str = Form(...),
    audit_remark: str = Form(""),
    db: Session = Depends(get_db),
):
    try:
        payload = KnowledgeReviewActionRequest(
            action="approve",
            audit_user=audit_user,
            audit_remark=audit_remark or None,
        )
        result = AdminReviewService(db).approve_knowledge(knowledge_id, payload)
        return _redirect(f"/admin/knowledge/{knowledge_id}", message=result["message"])
    except (AdminReviewServiceError, ValidationError) as exc:
        msg = exc.message if isinstance(exc, AdminReviewServiceError) else str(exc)
        return _redirect(f"/admin/knowledge/{knowledge_id}", error=msg)


@router.post("/admin/knowledge/{knowledge_id}/reject")
def admin_reject_knowledge(
    knowledge_id: int,
    audit_user: str = Form(...),
    audit_remark: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        payload = KnowledgeReviewActionRequest(
            action="reject",
            audit_user=audit_user,
            audit_remark=audit_remark,
        )
        result = AdminReviewService(db).reject_knowledge(knowledge_id, payload)
        return _redirect(f"/admin/knowledge/{knowledge_id}", message=result["message"])
    except (AdminReviewServiceError, ValidationError) as exc:
        msg = exc.message if isinstance(exc, AdminReviewServiceError) else str(exc)
        return _redirect(f"/admin/knowledge/{knowledge_id}", error=msg)
