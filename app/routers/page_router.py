from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.db.database import get_db
from app.schemas.knowledge_schema import KnowledgeAuditRequest, KnowledgeCreate, KnowledgeUpdate
from app.services.feedback_service import FeedbackService
from app.services.knowledge_service import KnowledgeService, KnowledgeServiceError
from app.services.question_service import QuestionService
from app.services.statistics_service import StatisticsService
from app.services.unanswered_service import UnansweredService

router = APIRouter(tags=["pages"])
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


def _redirect_knowledge_list(message: str | None = None, error: str | None = None) -> RedirectResponse:
    url = "/knowledge-cards"
    params: list[str] = []
    if message:
        params.append(f"msg={quote(message)}")
    if error:
        params.append(f"error={quote(error)}")
    if params:
        url = f"{url}?{'&'.join(params)}"
    return RedirectResponse(url=url, status_code=303)


def _redirect_knowledge_detail(card_id: int, message: str | None = None, error: str | None = None) -> RedirectResponse:
    url = f"/knowledge-cards/{card_id}"
    params: list[str] = []
    if message:
        params.append(f"msg={quote(message)}")
    if error:
        params.append(f"error={quote(error)}")
    if params:
        url = f"{url}?{'&'.join(params)}"
    return RedirectResponse(url=url, status_code=303)


def _build_form_payload(
    title: str,
    question: str,
    answer: str,
    system_name: str = "",
    module_name: str = "",
    tags: str = "",
    scene: str = "",
    reason_analysis: str = "",
    troubleshooting_steps: str = "",
    solution: str = "",
    risk_notice: str = "",
    source_group: str = "",
    source_user: str = "",
) -> dict:
    return {
        "title": title,
        "question": question,
        "answer": answer,
        "system_name": system_name,
        "module_name": module_name,
        "tags": tags,
        "scene": scene,
        "reason_analysis": reason_analysis,
        "troubleshooting_steps": troubleshooting_steps,
        "solution": solution,
        "risk_notice": risk_notice,
        "source_group": source_group,
        "source_user": source_user or "admin",
    }


def _normalize_pagination(page: int, page_size: int) -> tuple[int, int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    return page, page_size


def _db_error_message(exc: Exception) -> str:
    return (
        "数据库连接失败，请确认 MySQL 已启动、已执行 init_mysql.sql 建库，"
        "并已运行 python app/db/init_db.py 初始化表结构。"
        f" 详情: {exc}"
    )


@router.get("/ask-test", response_class=HTMLResponse)
def ask_test_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="ask_test.html",
        context=_page_context(request, "ask_test"),
    )


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=_page_context(request, "index"),
    )


@router.get("/knowledge-cards", response_class=HTMLResponse)
def knowledge_cards(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> HTMLResponse:
    page, page_size = _normalize_pagination(page, page_size)
    context = {"items": [], "total": 0, "page": page, "page_size": page_size, "db_error": None}
    try:
        result = KnowledgeService(db).list_for_page(page=page, page_size=page_size)
        context.update(result)
    except SQLAlchemyError as exc:
        context["db_error"] = _db_error_message(exc)
    return templates.TemplateResponse(
        request=request,
        name="knowledge_list.html",
        context=_page_context(request, "knowledge", **context),
    )


@router.get("/knowledge-cards/new", response_class=HTMLResponse)
def knowledge_card_new_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="knowledge_form.html",
        context=_page_context(
            request,
            "knowledge",
            form_title="新增知识卡片",
            form_action="/knowledge-cards/new",
            card={},
            form_error=None,
        ),
    )


@router.post("/knowledge-cards/new")
def knowledge_card_create(
    request: Request,
    db: Session = Depends(get_db),
    title: str = Form(...),
    question: str = Form(...),
    answer: str = Form(...),
    system_name: str = Form(""),
    module_name: str = Form(""),
    tags: str = Form(""),
    scene: str = Form(""),
    reason_analysis: str = Form(""),
    troubleshooting_steps: str = Form(""),
    solution: str = Form(""),
    risk_notice: str = Form(""),
    source_group: str = Form(""),
    source_user: str = Form("admin"),
):
    payload = _build_form_payload(
        title, question, answer, system_name, module_name, tags, scene,
        reason_analysis, troubleshooting_steps, solution, risk_notice,
        source_group, source_user,
    )
    try:
        card = KnowledgeService(db).create(KnowledgeCreate(**payload))
        return _redirect_knowledge_detail(card["id"], "知识卡片创建成功")
    except (KnowledgeServiceError, SQLAlchemyError, ValueError) as exc:
        return templates.TemplateResponse(
            request=request,
            name="knowledge_form.html",
            context=_page_context(
                request,
                "knowledge",
                form_title="新增知识卡片",
                form_action="/knowledge-cards/new",
                card=payload,
                form_error=str(exc),
            ),
            status_code=400,
        )


@router.get("/knowledge-cards/{card_id:int}", response_class=HTMLResponse)
def knowledge_card_detail(
    request: Request,
    card_id: int,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        card = KnowledgeService(db).get_detail(card_id)
        return templates.TemplateResponse(
            request=request,
            name="knowledge_detail.html",
            context=_page_context(request, "knowledge", card=card, page_error=None),
        )
    except KnowledgeServiceError as exc:
        return _redirect_knowledge_list(error=str(exc))
    except SQLAlchemyError as exc:
        return templates.TemplateResponse(
            request=request,
            name="knowledge_detail.html",
            context=_page_context(request, "knowledge", card={"id": card_id, "title": "加载失败"}, page_error=_db_error_message(exc)),
            status_code=500,
        )


@router.get("/knowledge-cards/{card_id:int}/edit", response_class=HTMLResponse)
def knowledge_card_edit_page(request: Request, card_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    try:
        card = KnowledgeService(db).get_detail(card_id)
        return templates.TemplateResponse(
            request=request,
            name="knowledge_form.html",
            context=_page_context(
                request,
                "knowledge",
                form_title="编辑知识卡片",
                form_action=f"/knowledge-cards/{card_id}/edit",
                card=card,
                form_error=None,
            ),
        )
    except KnowledgeServiceError as exc:
        return _redirect_knowledge_list(error=str(exc))
    except SQLAlchemyError as exc:
        return _redirect_knowledge_list(error=_db_error_message(exc))


@router.post("/knowledge-cards/{card_id:int}/edit")
def knowledge_card_update(
    request: Request,
    card_id: int,
    db: Session = Depends(get_db),
    title: str = Form(...),
    question: str = Form(...),
    answer: str = Form(...),
    system_name: str = Form(""),
    module_name: str = Form(""),
    tags: str = Form(""),
    scene: str = Form(""),
    reason_analysis: str = Form(""),
    troubleshooting_steps: str = Form(""),
    solution: str = Form(""),
    risk_notice: str = Form(""),
    source_group: str = Form(""),
    source_user: str = Form("admin"),
):
    payload = _build_form_payload(
        title, question, answer, system_name, module_name, tags, scene,
        reason_analysis, troubleshooting_steps, solution, risk_notice,
        source_group, source_user,
    )
    try:
        KnowledgeService(db).update(card_id, KnowledgeUpdate(**payload))
        return _redirect_knowledge_detail(card_id, "知识卡片更新成功")
    except (KnowledgeServiceError, SQLAlchemyError, ValueError) as exc:
        payload["id"] = card_id
        return templates.TemplateResponse(
            request=request,
            name="knowledge_form.html",
            context=_page_context(
                request,
                "knowledge",
                form_title="编辑知识卡片",
                form_action=f"/knowledge-cards/{card_id}/edit",
                card=payload,
                form_error=str(exc),
            ),
            status_code=400,
        )


@router.post("/knowledge-cards/{card_id:int}/submit-audit")
def knowledge_card_submit_audit(card_id: int, db: Session = Depends(get_db)):
    try:
        KnowledgeService(db).submit_audit(card_id)
        return _redirect_knowledge_list("已提交审核")
    except (KnowledgeServiceError, SQLAlchemyError) as exc:
        return _redirect_knowledge_list(error=str(exc))


@router.post("/knowledge-cards/{card_id:int}/audit")
def knowledge_card_audit(
    card_id: int,
    db: Session = Depends(get_db),
    audit_status: str = Form(...),
    audit_user: str = Form("admin"),
    audit_remark: str = Form(""),
):
    try:
        payload = KnowledgeAuditRequest(
            audit_status=audit_status,
            audit_user=audit_user,
            audit_remark=audit_remark or None,
        )
        KnowledgeService(db).audit(card_id, payload)
        msg = "审核通过" if audit_status == "approved" else "审核已拒绝"
        return _redirect_knowledge_list(msg)
    except (KnowledgeServiceError, SQLAlchemyError, ValueError) as exc:
        return _redirect_knowledge_list(error=str(exc))


@router.post("/knowledge-cards/{card_id:int}/enable")
def knowledge_card_enable(card_id: int, db: Session = Depends(get_db)):
    try:
        KnowledgeService(db).enable(card_id)
        return _redirect_knowledge_list("知识卡片已启用")
    except (KnowledgeServiceError, SQLAlchemyError) as exc:
        return _redirect_knowledge_list(error=str(exc))


@router.post("/knowledge-cards/{card_id:int}/disable")
def knowledge_card_disable(card_id: int, db: Session = Depends(get_db)):
    try:
        KnowledgeService(db).disable(card_id)
        return _redirect_knowledge_list("知识卡片已停用")
    except (KnowledgeServiceError, SQLAlchemyError) as exc:
        return _redirect_knowledge_list(error=str(exc))


@router.post("/knowledge-cards/{card_id:int}/delete")
def knowledge_card_delete(card_id: int, db: Session = Depends(get_db)):
    try:
        KnowledgeService(db).soft_delete(card_id)
        return _redirect_knowledge_list("知识卡片已删除")
    except (KnowledgeServiceError, SQLAlchemyError) as exc:
        return _redirect_knowledge_list(error=str(exc))


@router.get("/unanswered-questions", response_class=HTMLResponse)
def unanswered_questions(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    status: str | None = Query("pending"),
) -> HTMLResponse:
    page, page_size = _normalize_pagination(page, page_size)
    status_filter = status if status is not None else ""
    context = {
        "items": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
        "status_filter": status_filter,
        "db_error": None,
    }
    try:
        list_status = status if status else None
        result = UnansweredService(db).list_for_page(page=page, page_size=page_size, status=list_status)
        context.update(result)
        context["status_filter"] = status_filter
    except SQLAlchemyError as exc:
        context["db_error"] = _db_error_message(exc)
    return templates.TemplateResponse(
        request=request,
        name="unanswered_list.html",
        context=_page_context(request, "unanswered", **context),
    )


@router.get("/unanswered-questions/{unanswered_id:int}", response_class=HTMLResponse)
def unanswered_question_detail(
    request: Request,
    unanswered_id: int,
    db: Session = Depends(get_db),
    status: str | None = Query(None),
) -> HTMLResponse:
    context = {
        "item": None,
        "page_error": None,
        "status_filter": status or "pending",
    }
    try:
        item = UnansweredService(db).get_detail_for_page(unanswered_id)
        if item is None:
            context["page_error"] = "未命中问题不存在"
        else:
            context["item"] = item
    except SQLAlchemyError as exc:
        context["page_error"] = _db_error_message(exc)
    return templates.TemplateResponse(
        request=request,
        name="unanswered_detail.html",
        context=_page_context(request, "unanswered", **context),
    )


@router.get("/question-logs", response_class=HTMLResponse)
def question_logs(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> HTMLResponse:
    page, page_size = _normalize_pagination(page, page_size)
    context = {"items": [], "total": 0, "page": page, "page_size": page_size, "db_error": None}
    try:
        result = QuestionService(db).list_for_page(page=page, page_size=page_size)
        context.update(result)
    except SQLAlchemyError as exc:
        context["db_error"] = _db_error_message(exc)
    return templates.TemplateResponse(
        request=request,
        name="question_log_list.html",
        context=_page_context(request, "question_logs", **context),
    )


@router.get("/feedback", response_class=HTMLResponse)
def feedback_list(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    feedback_type: str | None = Query(None),
) -> HTMLResponse:
    page, page_size = _normalize_pagination(page, page_size)
    feedback_type_filter = feedback_type or ""
    context = {
        "items": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
        "feedback_type_filter": feedback_type_filter,
        "db_error": None,
    }
    try:
        list_type = feedback_type if feedback_type else None
        result = FeedbackService(db).list_for_page(
            page=page,
            page_size=page_size,
            feedback_type=list_type,
        )
        context.update(result)
        context["feedback_type_filter"] = feedback_type_filter
    except SQLAlchemyError as exc:
        context["db_error"] = _db_error_message(exc)
    return templates.TemplateResponse(
        request=request,
        name="feedback_list.html",
        context=_page_context(request, "feedback", **context),
    )


@router.get("/statistics", response_class=HTMLResponse)
def statistics(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    context = {
        "db_error": None,
        "dashboard": {
            "total_questions": 0,
            "matched_questions": 0,
            "missed_questions": 0,
            "unanswered_questions": 0,
            "match_rate": 0.0,
            "miss_rate": 0.0,
            "feedback_total": 0,
            "satisfaction_rate": 0.0,
            "total_knowledge_cards": 0,
            "approved_knowledge_cards": 0,
            "pending_knowledge_cards": 0,
            "useful_feedback_count": 0,
            "useless_feedback_count": 0,
            "need_human_feedback_count": 0,
            "top_unanswered_questions": [],
            "top_negative_feedback_questions": [],
        },
    }
    try:
        context["dashboard"] = StatisticsService(db).get_dashboard()
    except SQLAlchemyError as exc:
        context["db_error"] = _db_error_message(exc)
    return templates.TemplateResponse(
        request=request,
        name="statistics.html",
        context=_page_context(request, "statistics", **context),
    )
