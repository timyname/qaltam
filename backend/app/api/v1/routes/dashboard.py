from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.access import ActorContext, ensure_actor_matches_identity, require_workspace_roles
from backend.app.db.database import get_session
from backend.app.models.enums import WorkspaceRole
from backend.app.schemas.dashboard import (
    DashboardMacroResponse,
    DashboardMediumResponse,
    DashboardMicroResponse,
)
from backend.app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/macro", response_model=DashboardMacroResponse)
async def get_macro_dashboard(
    actor: ActorContext = Depends(
        require_workspace_roles(
            WorkspaceRole.OWNER,
            WorkspaceRole.CFO,
            WorkspaceRole.COO,
            WorkspaceRole.CASHIER,
        )
    ),
    session: AsyncSession = Depends(get_session),
) -> DashboardMacroResponse:
    service = DashboardService(session)
    return await service.get_macro_dashboard(actor.telegram_user_id)


@router.get("/medium", response_model=DashboardMediumResponse)
async def get_medium_dashboard(
    actor: ActorContext = Depends(
        require_workspace_roles(
            WorkspaceRole.OWNER,
            WorkspaceRole.CFO,
            WorkspaceRole.COO,
            WorkspaceRole.CASHIER,
        )
    ),
    session: AsyncSession = Depends(get_session),
) -> DashboardMediumResponse:
    service = DashboardService(session)
    return await service.get_medium_dashboard(actor.telegram_user_id)


@router.get("/micro", response_model=DashboardMicroResponse)
async def get_micro_dashboard(
    telegram_user_id: int | None = None,
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
) -> DashboardMicroResponse:
    target_user_id = telegram_user_id or actor.telegram_user_id
    ensure_actor_matches_identity(actor, telegram_user_id=target_user_id)
    service = DashboardService(session)
    return await service.get_micro_dashboard(target_user_id)
