from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.access import ActorContext, ensure_actor_matches_identity, require_workspace_roles
from backend.app.db.database import get_session
from backend.app.models.enums import WorkspaceRole
from backend.app.services.chat_service import ChatService

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])


@router.post("/start")
async def start_onboarding(
    telegram_user_id: int,
    telegram_chat_id: int,
    actor: ActorContext = Depends(
        require_workspace_roles(
            WorkspaceRole.OWNER,
            WorkspaceRole.CFO,
            WorkspaceRole.COO,
            WorkspaceRole.CASHIER,
            WorkspaceRole.FAMILY_MEMBER,
        )
    ),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    ensure_actor_matches_identity(
        actor,
        telegram_user_id=telegram_user_id,
        telegram_chat_id=telegram_chat_id,
    )
    service = ChatService(session)
    message = await service.start(telegram_user_id, telegram_chat_id)
    await session.commit()
    return {"message": message}
