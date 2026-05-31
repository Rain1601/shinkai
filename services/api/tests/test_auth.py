from shinkai_api.core.auth import build_auth_session, is_admin_token_valid
from shinkai_api.core.config import settings


def test_auth_session_is_admin_when_auth_disabled() -> None:
    previous_required = settings.auth_required
    previous_token = settings.admin_token
    previous_subscriber_tokens = settings.subscriber_tokens
    settings.auth_required = False
    settings.admin_token = None
    settings.subscriber_tokens = []
    try:
        session = build_auth_session(None)
        assert session.auth_required is False
        assert session.role == "admin"
        assert session.read_scope == "admin"
        assert "create_runs" in session.capabilities
        assert "read_run_process" in session.capabilities
        assert is_admin_token_valid(None)
    finally:
        settings.auth_required = previous_required
        settings.admin_token = previous_token
        settings.subscriber_tokens = previous_subscriber_tokens


def test_auth_session_requires_matching_admin_token() -> None:
    previous_required = settings.auth_required
    previous_token = settings.admin_token
    previous_subscriber_tokens = settings.subscriber_tokens
    settings.auth_required = True
    settings.admin_token = "secret-token"
    settings.subscriber_tokens = []
    try:
        viewer = build_auth_session(None)
        assert viewer.role == "viewer"
        assert viewer.read_scope == "public"
        assert "read_results" in viewer.capabilities
        assert "read_run_process" in viewer.capabilities
        assert "create_runs" not in viewer.capabilities
        assert build_auth_session("wrong-token").role == "viewer"
        admin = build_auth_session("secret-token")
        assert admin.role == "admin"
        assert "control_runs" in admin.capabilities
        assert not is_admin_token_valid("wrong-token")
        assert is_admin_token_valid("secret-token")
    finally:
        settings.auth_required = previous_required
        settings.admin_token = previous_token
        settings.subscriber_tokens = previous_subscriber_tokens


def test_subscriber_session_expands_read_scope_without_write_access() -> None:
    previous_required = settings.auth_required
    previous_token = settings.admin_token
    previous_subscriber_tokens = settings.subscriber_tokens
    settings.auth_required = True
    settings.admin_token = "secret-token"
    settings.subscriber_tokens = ["subscriber-token"]
    try:
        subscriber = build_auth_session("subscriber-token")
        assert subscriber.role == "subscriber"
        assert subscriber.read_scope == "subscriber"
        assert "read_results" in subscriber.capabilities
        assert "read_run_process" in subscriber.capabilities
        assert "read_extended_results" in subscriber.capabilities
        assert "create_runs" not in subscriber.capabilities
    finally:
        settings.auth_required = previous_required
        settings.admin_token = previous_token
        settings.subscriber_tokens = previous_subscriber_tokens
