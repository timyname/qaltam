from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.access import ActorContext, ensure_actor_matches_identity, require_workspace_roles
from backend.app.db.database import get_session
from backend.app.models.enums import WorkspaceRole
from backend.app.models.profile import UserProfile
from backend.app.schemas.profile import ProfilePreferencesResponse, ProfilePreferencesUpdateRequest
from backend.app.services.chat_service import ChatService

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


@router.patch("/preferences", response_model=ProfilePreferencesResponse)
async def update_profile_preferences(
    payload: ProfilePreferencesUpdateRequest,
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
) -> ProfilePreferencesResponse:
    ensure_actor_matches_identity(actor, telegram_user_id=payload.telegram_user_id)

    result = await session.execute(select(UserProfile).where(UserProfile.telegram_user_id == payload.telegram_user_id))
    profile = result.scalars().first()
    if profile is None:
        profile = await ChatService(session).get_or_create_profile(
            payload.telegram_user_id,
            actor.telegram_chat_id,
            fallback_language_code=payload.preferred_language,
        )

    profile.telegram_chat_id = actor.telegram_chat_id
    profile.preferred_language = payload.preferred_language
    await session.commit()

    return ProfilePreferencesResponse(
        telegram_user_id=payload.telegram_user_id,
        preferred_language=profile.preferred_language,
    )
