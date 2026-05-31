from shinkai_api.core.auth import build_auth_session, is_admin_token_valid
from shinkai_api.core.config import settings


def test_auth_session_is_admin_when_auth_disabled() -> None:
    previous_required = settings.auth_required
    previous_token = settings.admin_token
    settings.auth_required = False
    settings.admin_token = None
    try:
        session = build_auth_session(None)
        assert session.auth_required is False
        assert session.role == "admin"
        assert is_admin_token_valid(None)
    finally:
        settings.auth_required = previous_required
        settings.admin_token = previous_token


def test_auth_session_requires_matching_admin_token() -> None:
    previous_required = settings.auth_required
    previous_token = settings.admin_token
    settings.auth_required = True
    settings.admin_token = "secret-token"
    try:
        assert build_auth_session(None).role == "viewer"
        assert build_auth_session("wrong-token").role == "viewer"
        assert build_auth_session("secret-token").role == "admin"
        assert not is_admin_token_valid("wrong-token")
        assert is_admin_token_valid("secret-token")
    finally:
        settings.auth_required = previous_required
        settings.admin_token = previous_token
