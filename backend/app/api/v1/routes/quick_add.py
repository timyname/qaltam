from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.access import (
    ActorContext,
    ensure_actor_matches_identity,
    get_optional_actor_context,
    require_actor_context,
)
from backend.app.core.security import has_valid_local_api_key
from backend.app.db.database import get_session
from backend.app.schemas.transaction import (
    QuickAddPayload,
    QuickAddResponse,
    TransactionQueryPayload,
    TransactionQueryResponse,
    TransactionRead,
)
from backend.app.services.quick_add_service import QuickAddService
from backend.app.services.transaction_query_service import TransactionQueryService

router = APIRouter(prefix="/api/v1", tags=["quick-add"])


@router.post("/quick-add", response_model=QuickAddResponse)
@router.post("/transactions", response_model=QuickAddResponse)
async def quick_add(
    payload: QuickAddPayload,
    api_key_valid: bool = Depends(has_valid_local_api_key),
    actor: ActorContext | None = Depends(get_optional_actor_context),
    session: AsyncSession = Depends(get_session),
) -> QuickAddResponse:
    if not api_key_valid and payload.telegram_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mini App quick-add requires telegram_user_id. Shortcut mode requires a valid X-API-KEY.",
        )

    if not api_key_valid:
        if actor is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Mini App quick-add requires Telegram actor headers.",
            )
        ensure_actor_matches_identity(
            actor,
            telegram_user_id=payload.telegram_user_id,
            telegram_chat_id=payload.telegram_chat_id,
        )

    service = QuickAddService(session)
    result = await service.create(payload)
    return QuickAddResponse(
        transaction=TransactionRead.model_validate(result.transaction),
        account_type=result.account_type,
        route=result.route,
        normalized_text=result.normalized_text,
        message=result.message,
    )


@router.post("/transactions/query", response_model=TransactionQueryResponse)
async def query_transactions(
    payload: TransactionQueryPayload,
    actor: ActorContext = Depends(require_actor_context),
    session: AsyncSession = Depends(get_session),
) -> TransactionQueryResponse:
    ensure_actor_matches_identity(
        actor,
        telegram_user_id=payload.telegram_user_id,
        telegram_chat_id=payload.telegram_chat_id,
    )
    service = TransactionQueryService(session)
    return await service.answer_question(
        question=payload.question,
        telegram_user_id=payload.telegram_user_id,
    )
