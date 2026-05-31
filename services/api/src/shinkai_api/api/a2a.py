from fastapi import APIRouter, Depends

from shinkai_api.a2a import AgentMessage
from shinkai_api.core.auth import require_admin

router = APIRouter(prefix="/a2a/messages", tags=["a2a"])

_messages: list[AgentMessage] = []


@router.post("", response_model=AgentMessage, dependencies=[Depends(require_admin)])
async def create_message(message: AgentMessage) -> AgentMessage:
    _messages.append(message)
    return message


@router.get("", response_model=list[AgentMessage])
async def list_messages() -> list[AgentMessage]:
    return _messages
