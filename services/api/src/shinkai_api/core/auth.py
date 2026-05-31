from __future__ import annotations

import secrets
from typing import Literal

from fastapi import HTTPException, Request, status
from pydantic import BaseModel

from shinkai_api.core.config import settings

AuthRole = Literal["viewer", "subscriber", "admin"]
ReadScope = Literal["public", "subscriber", "admin"]

VIEWER_CAPABILITIES = [
    "read_results",
    "read_run_process",
]
SUBSCRIBER_CAPABILITIES = [
    *VIEWER_CAPABILITIES,
    "read_extended_results",
    "read_extended_history",
]
ADMIN_CAPABILITIES = [
    *SUBSCRIBER_CAPABILITIES,
    "create_runs",
    "control_runs",
    "release_checkpoints",
    "create_a2a_messages",
]


class AuthSession(BaseModel):
    auth_required: bool
    role: AuthRole
    read_scope: ReadScope
    capabilities: list[str]


def admin_auth_enabled() -> bool:
    return settings.auth_required or bool(settings.admin_token)


def extract_access_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token:
        return token.strip()
    header_token = request.headers.get("x-shinkai-access-token")
    if header_token:
        return header_token.strip()
    header_token = request.headers.get("x-shinkai-admin-token")
    return header_token.strip() if header_token else None


def extract_admin_token(request: Request) -> str | None:
    return extract_access_token(request)


def is_admin_token_valid(token: str | None) -> bool:
    if not admin_auth_enabled():
        return True
    if not token or not settings.admin_token:
        return False
    return secrets.compare_digest(token, settings.admin_token)


def is_subscriber_token_valid(token: str | None) -> bool:
    if not token:
        return False
    return any(secrets.compare_digest(token, candidate) for candidate in settings.subscriber_tokens)


def capabilities_for_role(role: AuthRole) -> list[str]:
    if role == "admin":
        return list(ADMIN_CAPABILITIES)
    if role == "subscriber":
        return list(SUBSCRIBER_CAPABILITIES)
    return list(VIEWER_CAPABILITIES)


def read_scope_for_role(role: AuthRole) -> ReadScope:
    if role == "admin":
        return "admin"
    if role == "subscriber":
        return "subscriber"
    return "public"


def build_auth_session(token: str | None) -> AuthSession:
    auth_required = admin_auth_enabled()
    if is_admin_token_valid(token):
        role: AuthRole = "admin"
    elif is_subscriber_token_valid(token):
        role = "subscriber"
    else:
        role = "viewer"
    return AuthSession(
        auth_required=auth_required,
        role=role,
        read_scope=read_scope_for_role(role),
        capabilities=capabilities_for_role(role),
    )


async def require_admin(request: Request) -> None:
    if is_admin_token_valid(extract_admin_token(request)):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="admin token required",
    )
