from fastapi import APIRouter, Request

from shinkai_api.core.auth import AuthSession, build_auth_session, extract_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/session", response_model=AuthSession)
async def get_auth_session(request: Request) -> AuthSession:
    return build_auth_session(extract_access_token(request))


@router.get("/whoami", response_model=AuthSession)
async def whoami(request: Request) -> AuthSession:
    """Alias of /session — modeled to match the OAuth-era frontend convention.

    Returns the same payload as ``/session`` so the web can call whichever
    name fits the surrounding code; both are read-only and return a viewer
    payload when no credentials are presented.
    """
    return build_auth_session(extract_access_token(request))
