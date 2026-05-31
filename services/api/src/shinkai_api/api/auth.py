from fastapi import APIRouter, Request

from shinkai_api.core.auth import AuthSession, build_auth_session, extract_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/session", response_model=AuthSession)
async def get_auth_session(request: Request) -> AuthSession:
    return build_auth_session(extract_access_token(request))
