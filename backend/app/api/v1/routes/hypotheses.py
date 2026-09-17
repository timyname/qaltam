from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.access import ActorContext, require_workspace_roles
from backend.app.db.database import get_session
from backend.app.models.enums import WorkspaceRole
from backend.app.schemas.hypothesis import HypothesisScoreRequest, HypothesisScoreResponse
from backend.app.services.scoring_engine import HypothesisScoringService

router = APIRouter(prefix="/api/v1/hypotheses", tags=["hypotheses"])


@router.post("/score-preview", response_model=HypothesisScoreResponse)
async def score_hypothesis_preview(
    payload: HypothesisScoreRequest,
    actor: ActorContext = Depends(
        require_workspace_roles(
            WorkspaceRole.OWNER,
            WorkspaceRole.CFO,
            WorkspaceRole.COO,
        )
    ),
    session: AsyncSession = Depends(get_session),
) -> HypothesisScoreResponse:
    service = HypothesisScoringService(session)
    return await service.preview(payload)
