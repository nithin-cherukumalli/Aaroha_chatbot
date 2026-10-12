from __future__ import annotations

import secrets
import uuid
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select

from app.api.dependencies import (
    check_rate_limit,
    csrf_protect,
    current_member,
    get_container,
    require_curator,
    serializer,
)
from app.api.schemas import (
    ChatRequest,
    LifecycleRequest,
    PendingQuestionRequest,
    SessionRequest,
)
from app.composition import Container
from app.domain import ContentMode, Role
from app.models import Document, Membership, PendingQuestion
from app.services.core import AppError

router = APIRouter(prefix="/api/v1")


def document_data(document: Document) -> dict:
    return {
        "id": str(document.id),
        "filename": document.filename,
        "type": document.file_type,
        "content_mode": document.content_mode,
        "status": document.state,
        "active": document.active,
        "warnings": document.warnings,
        "passage_count": document.passage_count,
        "added_at": document.created_at.isoformat() if document.created_at else None,
    }


@router.post("/auth/session", status_code=204)
async def create_session(
    payload: SessionRequest, response: Response, container: Container = Depends(get_container)
):
    user_id, email = await container.identity.verify_access_token(payload.access_token)
    csrf = secrets.token_urlsafe(32)
    token = serializer(container).dumps({"user_id": user_id, "email": email})
    secure = container.settings.app_env == "production"
    response.set_cookie(
        "ae_session", token, httponly=True, secure=secure, samesite="lax", max_age=60 * 60 * 8
    )
    response.set_cookie(
        "ae_csrf", csrf, httponly=False, secure=secure, samesite="lax", max_age=60 * 60 * 8
    )
    response.headers["X-CSRF-Token"] = csrf


@router.delete("/auth/session", status_code=204, dependencies=[Depends(csrf_protect)])
async def delete_session(response: Response):
    response.delete_cookie("ae_session")
    response.delete_cookie("ae_csrf")


@router.get("/identity")
def identity(member: Membership = Depends(current_member)):
    return {"data": {"id": str(member.id), "email": member.email, "role": member.role}}


@router.post("/chat", dependencies=[Depends(csrf_protect)])
async def chat(
    payload: ChatRequest,
    member: Membership = Depends(current_member),
    container: Container = Depends(get_container),
):
    check_rate_limit(member, container, container.settings.chat_requests_per_user_per_minute)
    result = await container.knowledge.answer(member, payload.question)
    return {"data": {**result, "request_id": str(uuid.uuid4())}}


@router.get("/documents")
def documents(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    _: Membership = Depends(require_curator),
    container: Container = Depends(get_container),
):
    items, total = container.knowledge.list_documents(page, per_page)
    return {
        "data": [document_data(item) for item in items],
        "meta": {"page": page, "per_page": per_page, "total": total},
    }


@router.post("/documents", status_code=202, dependencies=[Depends(csrf_protect)])
async def upload_document(
    file: UploadFile = File(...),
    content_mode: ContentMode = Form(ContentMode.GENERAL_DOCUMENT),
    replace_document_id: uuid.UUID | None = Form(default=None),
    member: Membership = Depends(require_curator),
    container: Container = Depends(get_container),
):
    data = await file.read(container.settings.max_upload_mb * 1024 * 1024 + 1)
    document, duplicate = await container.knowledge.upload(
        member, file.filename or "upload", data, content_mode, replace_document_id
    )
    return JSONResponse(
        {"data": {**document_data(document), "duplicate": duplicate}},
        status_code=200 if duplicate else 202,
        headers={"Location": f"/api/v1/documents/{document.id}"},
    )


@router.get("/documents/{document_id}")
def document_detail(
    document_id: uuid.UUID,
    _: Membership = Depends(require_curator),
    container: Container = Depends(get_container),
):
    return {"data": document_data(container.knowledge.get_document(document_id))}


@router.get("/documents/{document_id}/preview")
def document_preview(
    document_id: uuid.UUID,
    member: Membership = Depends(current_member),
    container: Container = Depends(get_container),
):
    document = container.knowledge.get_document(document_id)
    if member.role != Role.CURATOR.value and not (document.active and document.state == "READY"):
        raise AppError("forbidden", "This source is not available.", 403)
    with container.sessions() as session:
        from app.models import Passage

        passages = list(
            session.scalars(
                select(Passage)
                .where(Passage.document_id == document_id)
                .order_by(Passage.ordinal)
                .limit(30)
            )
        )
    return {
        "data": {
            **document_data(document),
            "passages": [
                {"id": str(p.id), "text": p.text, "location": p.source_location} for p in passages
            ],
        }
    }


@router.get("/documents/{document_id}/download")
async def document_download(
    document_id: uuid.UUID,
    member: Membership = Depends(current_member),
    container: Container = Depends(get_container),
):
    document = container.knowledge.get_document(document_id)
    if member.role != Role.CURATOR.value and not (document.active and document.state == "READY"):
        raise AppError("forbidden", "This source is not available.", 403)
    if not document.object_key:
        raise AppError("not_found", "The original document is no longer available.", 404)
    data = await container.storage.get(document.object_key)
    return StreamingResponse(
        iter([data]),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{PurePosixPath(document.filename).name}"'
        },
    )


@router.post("/documents/{document_id}/approve", dependencies=[Depends(csrf_protect)])
def approve(
    document_id: uuid.UUID,
    member: Membership = Depends(require_curator),
    container: Container = Depends(get_container),
):
    return {"data": document_data(container.knowledge.approve_document(member, document_id))}


@router.post("/documents/{document_id}/retry", dependencies=[Depends(csrf_protect)])
def retry(
    document_id: uuid.UUID,
    _: Membership = Depends(require_curator),
    container: Container = Depends(get_container),
):
    return {"data": document_data(container.knowledge.retry_document(document_id))}


@router.patch("/documents/{document_id}", dependencies=[Depends(csrf_protect)])
def document_lifecycle(
    document_id: uuid.UUID,
    payload: LifecycleRequest,
    _: Membership = Depends(require_curator),
    container: Container = Depends(get_container),
):
    return {
        "data": document_data(container.knowledge.transition_document(document_id, payload.action))
    }


@router.get("/pending-questions")
def pending_questions(
    page: int = Query(1, ge=1),
    _: Membership = Depends(require_curator),
    container: Container = Depends(get_container),
):
    with container.sessions() as session:
        rows = list(
            session.scalars(
                select(PendingQuestion)
                .order_by(PendingQuestion.created_at.desc())
                .offset((page - 1) * 30)
                .limit(30)
            )
        )
    return {
        "data": [
            {
                "id": str(row.id),
                "question": row.question,
                "state": row.state,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


@router.patch("/pending-questions/{question_id}", dependencies=[Depends(csrf_protect)])
def resolve_question(
    question_id: uuid.UUID,
    payload: PendingQuestionRequest,
    _: Membership = Depends(require_curator),
    container: Container = Depends(get_container),
):
    with container.sessions() as session:
        item = session.get(PendingQuestion, question_id)
        if not item:
            raise AppError("not_found", "Question not found.", 404)
        item.state = payload.state
        session.commit()
    return {"data": {"id": str(item.id), "state": item.state}}


@router.get("/operator/readiness")
async def readiness(
    _: Membership = Depends(require_curator), container: Container = Depends(get_container)
):
    vector = await container.index.health()
    with container.sessions() as session:
        database_ok = session.scalar(select(func.count()).select_from(Membership)) is not None
    return {
        "data": {
            "database": "ok" if database_ok else "degraded",
            "vector": "ok" if vector.ok else "degraded",
            "storage": "configured" if container.settings.supabase_url else "degraded",
        }
    }
