"""WeCom callback routes — URL verify, real XML, and mock JSON."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.db.database import get_db
from app.services.wecom_callback_service import WecomCallbackService
from app.wecom.schemas import WecomMockCallbackRequest

router = APIRouter(prefix="/api/wecom", tags=["wecom"])


@router.get("/callback")
def wecom_url_verify(
    msg_signature: str | None = Query(default=None),
    timestamp: str | None = Query(default=None),
    nonce: str | None = Query(default=None),
    echostr: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    service = WecomCallbackService(db)
    result = service.verify_callback_url(
        msg_signature=msg_signature,
        timestamp=timestamp,
        nonce=nonce,
        echostr=echostr,
    )
    return PlainTextResponse(content=result)


@router.post("/callback", response_model=None)
async def wecom_real_callback(
    request: Request,
    msg_signature: str | None = Query(default=None),
    timestamp: str | None = Query(default=None),
    nonce: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> Response:
    if not settings.wecom_enabled:
        return JSONResponse(status_code=503, content={"error": "wecom disabled"})

    service = WecomCallbackService(db)
    body = (await request.body()).decode("utf-8")
    xml_body = service.handle_real_callback(
        body,
        msg_signature=msg_signature,
        timestamp=timestamp,
        nonce=nonce,
    )
    return Response(content=xml_body, media_type="application/xml")


@router.post("/mock/callback", response_model=None)
def wecom_mock_callback(
    payload: WecomMockCallbackRequest,
    db: Session = Depends(get_db),
) -> Response:
    service = WecomCallbackService(db)
    xml_body = service.handle_mock_callback(payload)
    return Response(content=xml_body, media_type="application/xml")
