from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status
from pydantic import BaseModel

from shinkai_api.core.config import settings


class AuthSession(BaseModel):
    auth_required: bool
    role: str


def admin_auth_enabled() -> bool:
    return settings.auth_required or bool(settings.admin_token)


def extract_admin_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token:
        return token.strip()
    header_token = request.headers.get("x-shinkai-admin-token")
    return header_token.strip() if header_token else None


def is_admin_token_valid(token: str | None) -> bool:
    if not admin_auth_enabled():
        return True
    if not token or not settings.admin_token:
        return False
    return secrets.compare_digest(token, settings.admin_token)


def build_auth_session(token: str | None) -> AuthSession:
    auth_required = admin_auth_enabled()
    role = "admin" if is_admin_token_valid(token) else "viewer"
    return AuthSession(auth_required=auth_required, role=role)


async def require_admin(request: Request) -> None:
    if is_admin_token_valid(extract_admin_token(request)):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="admin token required",
    )
