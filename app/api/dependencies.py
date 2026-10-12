from __future__ import annotations

import secrets
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select

from app.composition import Container
from app.domain import Role
from app.models import Membership, RateCounter


def get_container(request: Request) -> Container:
    return request.app.state.container


def serializer(container: Container) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        container.settings.session_secret.get_secret_value(), salt="ai-engineering-session"
    )


async def current_member(
    request: Request, container: Container = Depends(get_container)
) -> Membership:
    value = request.cookies.get("ae_session")
    if not value:
        raise HTTPException(401, detail="Sign in to continue.")
    try:
        identity = serializer(container).loads(value, max_age=60 * 60 * 8)
    except BadSignature as exc:
        raise HTTPException(401, detail="Your session has expired. Please sign in again.") from exc
    member = container.knowledge.member_for_identity(identity["user_id"], identity.get("email"))
    if not member:
        raise HTTPException(403, detail="Your account does not have access to this knowledge base.")
    return member


def require_curator(member: Membership = Depends(current_member)) -> Membership:
    if member.role != Role.CURATOR.value:
        raise HTTPException(403, detail="Curator access is required for this action.")
    return member


async def csrf_protect(
    request: Request,
    x_csrf_token: str | None = Header(default=None),
    container: Container = Depends(get_container),
) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    cookie = request.cookies.get("ae_csrf")
    if not cookie or not x_csrf_token or not secrets.compare_digest(cookie, x_csrf_token):
        raise HTTPException(
            403, detail="Your session could not be verified. Refresh and try again."
        )


def check_rate_limit(member: Membership, container: Container, limit: int) -> None:
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    key = f"chat:{member.id}"
    with container.sessions.begin() as session:
        counter = session.scalar(
            select(RateCounter)
            .where(RateCounter.key == key, RateCounter.window_start == now)
            .with_for_update()
        )
        if not counter:
            counter = RateCounter(key=key, window_start=now, count=0)
            session.add(counter)
        counter.count += 1
        if counter.count > limit:
            raise HTTPException(
                429, detail="You have reached the request limit. Please try again in a minute."
            )
