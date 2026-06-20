"""页面路由（Jinja2 管理后台与问答测试页）。"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.db.database import get_db
from app.schemas.document_schema import DocTypeInput, DocumentUploadMeta
from app.schemas.knowledge_schema import KnowledgeAuditRequest, KnowledgeCreate, KnowledgeUpdate
from app.services.document_service import DocumentService, DocumentServiceError
from app.services.feedback_service import FeedbackService
from app.services.knowledge_service import KnowledgeService, KnowledgeServiceError
from app.services.operation_dashboard_service import OperationDashboardService
from app.services.question_service import QuestionService
from app.services.statistics_service import StatisticsService
from app.services.unanswered_service import UnansweredService

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


def _page_context(request: Request, active_page: str, **extra) -> dict:
    """构建 Jinja2 模板公共上下文（导航、环境信息、闪存消息）。"""
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
    """重定向到知识卡片列表，可选携带成功/错误提示。"""
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
    """重定向到知识卡片详情页。"""
    url = f"/knowledge-cards/{card_id}"
    params: list[str] = []
    if message:
        params.append(f"msg={quote(message)}")
    if error:
        params.append(f"error={quote(error)}")
    if params:
        url = f"{url}?{'&'.join(params)}"
    return RedirectResponse(url=url, status_code=303)


def _redirect_document_list(message: str | None = None, error: str | None = None) -> RedirectResponse:
    """重定向到文档列表，可选携带成功/错误提示。"""
    url = "/documents"
    params: list[str] = []
    if message:
        params.append(f"msg={quote(message)}")
    if error:
        params.append(f"error={quote(error)}")
    if params:
        url = f"{url}?{'&'.join(params)}"
    return RedirectResponse(url=url, status_code=303)


def _redirect_document_detail(doc_id: int, message: str | None = None, error: str | None = None) -> RedirectResponse:
    """重定向到文档详情页。"""
    url = f"/documents/{doc_id}"
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
    """将表单字段组装为知识卡片 payload 字典。"""
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
    """校正分页参数（页码≥1，每页条数上限 MAX_PAGE_SIZE）。"""
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    return page, page_size


def _db_error_message(exc: Exception) -> str:
    """将数据库异常转为面向用户的友好提示。"""
    return (
        "数据库连接失败，请确认 MySQL 已启动、已执行 init_mysql.sql 建库，"
        "并已运行 python app/db/init_db.py 初始化表结构。"
        f" 详情: {exc}"
    )


@router.get("/ask-test", response_class=HTMLResponse)
def ask_test_page(request: Request) -> HTMLResponse:
    """问答联调测试页。"""
    return templates.TemplateResponse(
        request=request,
        name="ask_test.html",
        context=_page_context(request, "ask_test"),
    )


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """管理后台首页。"""
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
    """知识卡片列表页。"""
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
    """新增知识卡片表单页。"""
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
    """提交新建知识卡片表单。"""
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
    """知识卡片详情页。"""
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
    """编辑知识卡片表单页。"""
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
    """提交编辑知识卡片表单。"""
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
    """提交知识卡片进入待审核状态。"""
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
    """审核知识卡片（通过/拒绝）。"""
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
    """启用知识卡片。"""
    try:
        KnowledgeService(db).enable(card_id)
        return _redirect_knowledge_list("知识卡片已启用")
    except (KnowledgeServiceError, SQLAlchemyError) as exc:
        return _redirect_knowledge_list(error=str(exc))


@router.post("/knowledge-cards/{card_id:int}/disable")
def knowledge_card_disable(card_id: int, db: Session = Depends(get_db)):
    """停用知识卡片。"""
    try:
        KnowledgeService(db).disable(card_id)
        return _redirect_knowledge_list("知识卡片已停用")
    except (KnowledgeServiceError, SQLAlchemyError) as exc:
        return _redirect_knowledge_list(error=str(exc))


@router.post("/knowledge-cards/{card_id:int}/delete")
def knowledge_card_delete(card_id: int, db: Session = Depends(get_db)):
    """软删除知识卡片。"""
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
    """未命中问题列表页。"""
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
    """未命中问题详情页（含草稿预览与转化）。"""
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
    """问答日志列表页。"""
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
    """用户反馈列表页。"""
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
    """统计看板页面。"""
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


@router.get("/operation-dashboard", response_class=HTMLResponse)
def operation_dashboard(
    request: Request,
    days: int = Query(7, ge=1, le=365),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """增强阶段5：运营看板页面。"""
    context: dict = {"db_error": None, "dashboard": None, "days": days}
    try:
        context["dashboard"] = OperationDashboardService(db).get_dashboard_view_model(days=days)
    except SQLAlchemyError as exc:
        context["db_error"] = _db_error_message(exc)
    return templates.TemplateResponse(
        request=request,
        name="operation_dashboard.html",
        context=_page_context(request, "operation_dashboard", **context),
    )


@router.get("/documents", response_class=HTMLResponse)
def document_list(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> HTMLResponse:
    """文档知识库列表页。"""
    page, page_size = _normalize_pagination(page, page_size)
    context = {"items": [], "total": 0, "page": page, "page_size": page_size, "db_error": None}
    try:
        result = DocumentService(db).list_for_page(page=page, page_size=page_size)
        context.update(result)
    except SQLAlchemyError as exc:
        context["db_error"] = _db_error_message(exc)
    return templates.TemplateResponse(
        request=request,
        name="document_list.html",
        context=_page_context(request, "documents", **context),
    )


@router.get("/documents/upload", response_class=HTMLResponse)
def document_upload_page(request: Request) -> HTMLResponse:
    """文档上传页。"""
    return templates.TemplateResponse(
        request=request,
        name="document_upload.html",
        context=_page_context(request, "documents", form={}, form_error=None),
    )


@router.post("/documents/upload")
async def document_upload_submit(
    request: Request,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    doc_name: str = Form(...),
    doc_type: DocTypeInput = Form("other"),
    system_name: str = Form(""),
    module_name: str = Form(""),
    version: str = Form(""),
):
    """提交文档上传表单。"""
    form_data = {
        "doc_name": doc_name,
        "doc_type": doc_type,
        "system_name": system_name,
        "module_name": module_name,
        "version": version,
    }
    try:
        meta = DocumentUploadMeta(**form_data)
        doc = await DocumentService(db).upload(file, meta)
        message = "文档上传成功"
        if doc.get("parse_status") == "failed":
            message = "文档已上传，但解析失败，请查看详情"
        elif doc.get("parse_status") == "parsed":
            message = f"文档上传并解析成功，共 {doc.get('chunk_count', 0)} 个切片"
        return _redirect_document_detail(doc["id"], message)
    except (DocumentServiceError, SQLAlchemyError, ValueError) as exc:
        return templates.TemplateResponse(
            request=request,
            name="document_upload.html",
            context=_page_context(
                request,
                "documents",
                form=form_data,
                form_error=str(exc),
            ),
            status_code=400,
        )


@router.get("/documents/{doc_id:int}", response_class=HTMLResponse)
def document_detail(
    request: Request,
    doc_id: int,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """文档详情与切片预览页。"""
    context = {
        "doc": None,
        "chunks": [],
        "chunk_total": 0,
        "page_error": None,
    }
    try:
        service = DocumentService(db)
        doc = service.get_detail(doc_id)
        chunk_result = service.list_chunks(doc_id, page=1, page_size=200)
        context["doc"] = doc
        context["chunks"] = chunk_result["items"]
        context["chunk_total"] = chunk_result["total"]
    except DocumentServiceError as exc:
        context["page_error"] = exc.message
    except SQLAlchemyError as exc:
        context["page_error"] = _db_error_message(exc)
    return templates.TemplateResponse(
        request=request,
        name="document_detail.html",
        context=_page_context(request, "documents", **context),
    )


@router.post("/documents/{doc_id:int}/enable")
def document_enable_page(doc_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    try:
        DocumentService(db).enable(doc_id)
        return _redirect_document_detail(doc_id, "文档已启用")
    except (DocumentServiceError, SQLAlchemyError) as exc:
        return _redirect_document_detail(doc_id, error=str(exc))


@router.post("/documents/{doc_id:int}/disable")
def document_disable_page(doc_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    try:
        DocumentService(db).disable(doc_id)
        return _redirect_document_detail(doc_id, "文档已禁用")
    except (DocumentServiceError, SQLAlchemyError) as exc:
        return _redirect_document_detail(doc_id, error=str(exc))


@router.post("/documents/{doc_id:int}/reparse")
def document_reparse_page(doc_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    try:
        doc = DocumentService(db).reparse(doc_id)
        message = "重新解析完成"
        if doc.get("parse_status") == "failed":
            message = "重新解析失败，请查看详情"
        return _redirect_document_detail(doc_id, message)
    except (DocumentServiceError, SQLAlchemyError) as exc:
        return _redirect_document_detail(doc_id, error=str(exc))


@router.post("/documents/{doc_id:int}/sync-vector")
def document_sync_vector_page(doc_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    try:
        from app.services.document_vector_sync_service import DocumentVectorSyncService

        stats = DocumentVectorSyncService(db).sync_document(doc_id)
        message = f"向量同步完成：成功 {stats.get('synced', 0)}，失败 {stats.get('failed', 0)}"
        return _redirect_document_detail(doc_id, message)
    except (DocumentServiceError, SQLAlchemyError, ValueError) as exc:
        return _redirect_document_detail(doc_id, error=str(exc))


@router.post("/documents/{doc_id:int}/delete-vector")
def document_delete_vector_page(doc_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    try:
        from app.services.document_vector_sync_service import DocumentVectorSyncService

        DocumentVectorSyncService(db).delete_document_vectors(doc_id)
        return _redirect_document_detail(doc_id, "文档向量已删除")
    except (DocumentServiceError, SQLAlchemyError, ValueError) as exc:
        return _redirect_document_detail(doc_id, error=str(exc))


@router.post("/documents/{doc_id:int}/delete")
def document_delete_page(doc_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    try:
        DocumentService(db).delete(doc_id)
        return _redirect_document_list("文档已删除")
    except (DocumentServiceError, SQLAlchemyError) as exc:
        return _redirect_document_detail(doc_id, error=str(exc))
