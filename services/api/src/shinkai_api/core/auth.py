from __future__ import annotations

import secrets
from typing import Any, Literal

import jwt
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
    # Optional identity fields populated when the session comes from an
    # OAuth-minted JWT rather than a static admin token.
    email: str | None = None
    name: str | None = None
    provider: str | None = None


def admin_auth_enabled() -> bool:
    return (
        settings.auth_required
        or bool(settings.admin_token)
        or bool(settings.session_jwt_secret)
    )


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


def _normalise_email(email: str | None) -> str:
    return (email or "").strip().lower()


def _is_owner_email(email: str | None) -> bool:
    needle = _normalise_email(email)
    if not needle:
        return False
    haystack = {_normalise_email(item) for item in settings.owner_emails}
    return needle in haystack


def decode_session_jwt(token: str | None) -> dict[str, Any] | None:
    """Verify a JWT minted by the web layer's NextAuth callback.

    Returns the decoded claims dict (with ``email`` / ``role`` / ``name`` /
    ``provider`` fields) when valid, or ``None`` on any failure. Never raises
    so callers can fall through to the legacy admin_token path.
    """
    if not token or not settings.session_jwt_secret:
        return None
    try:
        claims = jwt.decode(
            token,
            settings.session_jwt_secret,
            algorithms=[settings.session_jwt_algorithm],
            options={"require": ["exp"]},
        )
    except jwt.PyJWTError:
        return None
    if not isinstance(claims, dict):
        return None
    return claims


def is_admin_token_valid(token: str | None) -> bool:
    if not admin_auth_enabled():
        return True
    # Path 1 — legacy: a static admin token compared with constant time.
    if token and settings.admin_token:
        if secrets.compare_digest(token, settings.admin_token):
            return True
    # Path 2 — OAuth: a JWT signed with the shared session secret whose
    # claims grant the admin role (or whose email is on the owner list).
    claims = decode_session_jwt(token)
    if claims:
        if str(claims.get("role") or "") == "admin":
            return True
        if _is_owner_email(claims.get("email")):
            return True
    return False


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
    email: str | None = None
    name: str | None = None
    provider: str | None = None
    if is_admin_token_valid(token):
        role: AuthRole = "admin"
        claims = decode_session_jwt(token)
        if claims:
            email = claims.get("email") or None
            name = claims.get("name") or None
            provider = claims.get("provider") or None
    elif is_subscriber_token_valid(token):
        role = "subscriber"
    else:
        # JWT claims that don't reach admin still carry an identity if the
        # signature is valid — useful for showing "signed in as X (read-only)".
        claims = decode_session_jwt(token)
        if claims:
            role = "viewer"
            email = claims.get("email") or None
            name = claims.get("name") or None
            provider = claims.get("provider") or None
        else:
            role = "viewer"
    return AuthSession(
        auth_required=auth_required,
        role=role,
        read_scope=read_scope_for_role(role),
        capabilities=capabilities_for_role(role),
        email=email,
        name=name,
        provider=provider,
    )


async def require_admin(request: Request) -> None:
    if is_admin_token_valid(extract_admin_token(request)):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="admin token or signed-in owner session required",
    )
