from __future__ import annotations

import time

import jwt
import pytest
from fastapi import HTTPException

from shinkai_api.core.auth import (
    build_auth_session,
    decode_session_jwt,
    is_admin_token_valid,
)
from shinkai_api.core.config import settings

SECRET = "test-secret-32-chars-min-padding-padding"


def _mint(claims: dict[str, object]) -> str:
    payload = {
        "exp": int(time.time()) + 600,
        "iat": int(time.time()),
        **claims,
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


@pytest.fixture
def jwt_secret(monkeypatch):
    monkeypatch.setattr(settings, "session_jwt_secret", SECRET)
    monkeypatch.setattr(settings, "session_jwt_algorithm", "HS256")
    monkeypatch.setattr(settings, "owner_emails", ["owner@example.com"])
    monkeypatch.setattr(settings, "admin_token", None)
    yield


def test_jwt_admin_role_grants_admin(jwt_secret) -> None:
    token = _mint({"email": "owner@example.com", "role": "admin", "name": "Owner"})
    assert is_admin_token_valid(token) is True
    session = build_auth_session(token)
    assert session.role == "admin"
    assert session.email == "owner@example.com"


def test_jwt_owner_email_without_role_still_admin(jwt_secret) -> None:
    token = _mint({"email": "owner@example.com", "role": "viewer"})
    assert is_admin_token_valid(token) is True


def test_jwt_non_owner_is_viewer(jwt_secret) -> None:
    token = _mint({"email": "stranger@example.com", "role": "viewer"})
    assert is_admin_token_valid(token) is False
    session = build_auth_session(token)
    assert session.role == "viewer"
    assert session.email == "stranger@example.com"  # identity is preserved


def test_jwt_expired_token_rejected(jwt_secret) -> None:
    payload = {
        "exp": int(time.time()) - 60,  # expired 60s ago
        "email": "owner@example.com",
        "role": "admin",
    }
    token = jwt.encode(payload, SECRET, algorithm="HS256")
    assert decode_session_jwt(token) is None
    assert is_admin_token_valid(token) is False


def test_jwt_wrong_signature_rejected(jwt_secret) -> None:
    payload = {
        "exp": int(time.time()) + 600,
        "email": "owner@example.com",
        "role": "admin",
    }
    bad_token = jwt.encode(payload, "wrong-secret-key", algorithm="HS256")
    assert decode_session_jwt(bad_token) is None
    assert is_admin_token_valid(bad_token) is False


def test_require_admin_blocks_anonymous(jwt_secret) -> None:
    from fastapi import Request

    from shinkai_api.core.auth import require_admin

    scope = {
        "type": "http",
        "headers": [],
    }
    request = Request(scope=scope)  # type: ignore[arg-type]

    import asyncio

    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_admin(request))
    assert exc.value.status_code == 403


def test_legacy_admin_token_still_works(monkeypatch) -> None:
    monkeypatch.setattr(settings, "session_jwt_secret", None)
    monkeypatch.setattr(settings, "admin_token", "legacy-token-xyz")
    assert is_admin_token_valid("legacy-token-xyz") is True
    assert is_admin_token_valid("wrong-token") is False
