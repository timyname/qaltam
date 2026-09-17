from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.access import ActorContext, ensure_actor_matches_identity, require_workspace_roles
from backend.app.core.config import get_settings
from backend.app.db.database import get_session
from backend.app.localization import normalize_language, text
from backend.app.models.enums import WorkspaceRole
from backend.app.schemas.statements import (
    MatchedClarificationRuleRead,
    StatementDetailRead,
    StatementHistoryEntryRead,
    StatementHistoryResponse,
    PendingStatementItemRead,
    PendingStatementRead,
    StatementClarificationPayload,
    StatementClarificationResponse,
    StatementImportResultRead,
    StatementImportTextPayload,
    StatementWorkbenchRead,
    StatementStatusSnapshotRead,
    StatementWorkbenchStatusRead,
)
from backend.app.services.statement_import_service import (
    ActiveStatementImportConflictError,
    StatementImportService,
)

router = APIRouter(prefix="/api/v1/statements", tags=["statements"])
SUPPORTED_STATEMENT_EXTENSIONS = {".pdf", ".csv", ".xlsx", ".xls"}


def _statement_import_blocked_detail(
    exc: ActiveStatementImportConflictError,
    *,
    language: str,
) -> str:
    return text(
        "statement_import_blocked",
        language,
        name=exc.statement_name,
        count=exc.remaining_clarifications,
    )


def _statement_import_failed_detail(exc: Exception, *, language: str) -> str:
    return text("statement_import_failed", language, details=str(exc))


def _statement_clarification_failed_detail(exc: Exception, *, language: str) -> str:
    return text("statement_clarification_failed", language, details=str(exc))


async def _run_statement_clarification(operation, *, language: str) -> str | None:
    try:
        return await operation
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_statement_clarification_failed_detail(exc, language=language),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_statement_clarification_failed_detail(exc, language=language),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_statement_clarification_failed_detail(exc, language=language),
        ) from exc


@router.get("/pending", response_model=PendingStatementRead | None)
async def get_pending_statement(
    telegram_user_id: int | None = Query(default=None),
    language: str | None = Query(None),
    actor: ActorContext = Depends(
        require_workspace_roles(
            WorkspaceRole.OWNER,
            WorkspaceRole.CFO,
            WorkspaceRole.COO,
            WorkspaceRole.CASHIER,
        )
    ),
    session: AsyncSession = Depends(get_session),
) -> PendingStatementRead | None:
    target_user_id = telegram_user_id or actor.telegram_user_id
    ensure_actor_matches_identity(actor, telegram_user_id=target_user_id)
    service = StatementImportService(session)
    return await _build_pending_response(
        service,
        target_user_id,
        language=normalize_language(language, default="en"),
    )


@router.get("/history", response_model=StatementHistoryResponse)
async def get_statement_history(
    telegram_user_id: int | None = Query(default=None),
    limit: int = Query(6, ge=1, le=20),
    actor: ActorContext = Depends(
        require_workspace_roles(
            WorkspaceRole.OWNER,
            WorkspaceRole.CFO,
            WorkspaceRole.COO,
            WorkspaceRole.CASHIER,
        )
    ),
    session: AsyncSession = Depends(get_session),
) -> StatementHistoryResponse:
    target_user_id = telegram_user_id or actor.telegram_user_id
    ensure_actor_matches_identity(actor, telegram_user_id=target_user_id)
    service = StatementImportService(session)
    history = await service.get_recent_history(target_user_id, limit=limit)
    return StatementHistoryResponse(items=[_build_history_entry_response(item) for item in history])


@router.get("/workbench", response_model=StatementWorkbenchRead)
async def get_statement_workbench(
    telegram_user_id: int | None = Query(default=None),
    language: str | None = Query(None),
    limit: int = Query(6, ge=1, le=20),
    actor: ActorContext = Depends(
        require_workspace_roles(
            WorkspaceRole.OWNER,
            WorkspaceRole.CFO,
            WorkspaceRole.COO,
            WorkspaceRole.CASHIER,
        )
    ),
    session: AsyncSession = Depends(get_session),
) -> StatementWorkbenchRead:
    target_user_id = telegram_user_id or actor.telegram_user_id
    ensure_actor_matches_identity(actor, telegram_user_id=target_user_id)
    service = StatementImportService(session)
    return await _build_workbench_response(
        service,
        target_user_id,
        language=normalize_language(language, default="en"),
        history_limit=limit,
    )


@router.get("/status", response_model=StatementWorkbenchStatusRead)
async def get_statement_status(
    telegram_user_id: int | None = Query(default=None),
    language: str | None = Query(None),
    actor: ActorContext = Depends(
        require_workspace_roles(
            WorkspaceRole.OWNER,
            WorkspaceRole.CFO,
            WorkspaceRole.COO,
            WorkspaceRole.CASHIER,
        )
    ),
    session: AsyncSession = Depends(get_session),
) -> StatementWorkbenchStatusRead:
    target_user_id = telegram_user_id or actor.telegram_user_id
    ensure_actor_matches_identity(actor, telegram_user_id=target_user_id)
    service = StatementImportService(session)
    workbench = await _build_workbench_response(
        service,
        target_user_id,
        language=normalize_language(language, default="en"),
        history_limit=1,
    )
    return StatementWorkbenchStatusRead(
        latest_status=workbench.latest_status,
        pending=workbench.pending,
    )


@router.get("/detail/{statement_id}", response_model=StatementDetailRead)
async def get_statement_detail(
    statement_id: int,
    telegram_user_id: int | None = Query(default=None),
    language: str | None = Query(None),
    actor: ActorContext = Depends(
        require_workspace_roles(
            WorkspaceRole.OWNER,
            WorkspaceRole.CFO,
            WorkspaceRole.COO,
            WorkspaceRole.CASHIER,
        )
    ),
    session: AsyncSession = Depends(get_session),
) -> StatementDetailRead:
    target_user_id = telegram_user_id or actor.telegram_user_id
    ensure_actor_matches_identity(actor, telegram_user_id=target_user_id)
    service = StatementImportService(session)
    detail = await service.get_statement_detail(target_user_id, statement_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=text("statement_no_pending_for_user", normalize_language(language, default="en")),
        )

    pending = await _build_pending_response(service, target_user_id, language=normalize_language(language, default="en"))
    if not pending or pending.statement_id != detail.imported_statement_id:
        pending = None
    return _build_statement_detail_response(detail, pending=pending)


@router.get("/detail/{statement_id}/source")
async def download_statement_source(
    statement_id: int,
    telegram_user_id: int | None = Query(default=None),
    language: str | None = Query(None),
    actor: ActorContext = Depends(
        require_workspace_roles(
            WorkspaceRole.OWNER,
            WorkspaceRole.CFO,
            WorkspaceRole.COO,
            WorkspaceRole.CASHIER,
        )
    ),
    session: AsyncSession = Depends(get_session),
):
    normalized_language = normalize_language(language, default="en")
    target_user_id = telegram_user_id or actor.telegram_user_id
    ensure_actor_matches_identity(actor, telegram_user_id=target_user_id)
    service = StatementImportService(session)
    source = await service.get_statement_source(target_user_id, statement_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=text("statement_no_pending_for_user", normalized_language),
        )

    if source.file_path:
        return FileResponse(
            source.file_path,
            media_type=source.media_type,
            filename=source.filename,
        )

    return Response(
        content=source.content or b"",
        media_type=source.media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(source.filename)}"},
    )


@router.post("/import-text", response_model=StatementImportResultRead)
async def import_statement_text(
    payload: StatementImportTextPayload,
    actor: ActorContext = Depends(
        require_workspace_roles(
            WorkspaceRole.OWNER,
            WorkspaceRole.CFO,
            WorkspaceRole.COO,
            WorkspaceRole.CASHIER,
        )
    ),
    session: AsyncSession = Depends(get_session),
) -> StatementImportResultRead:
    ensure_actor_matches_identity(
        actor,
        telegram_user_id=payload.telegram_user_id,
        telegram_chat_id=payload.telegram_chat_id,
    )
    service = StatementImportService(session)
    language = normalize_language(payload.language, default="en")
    try:
        result = await service.import_text(
            telegram_user_id=payload.telegram_user_id,
            telegram_chat_id=payload.telegram_chat_id,
            raw_text=payload.raw_text,
            language=language,
        )
    except ActiveStatementImportConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_statement_import_blocked_detail(exc, language=language),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_statement_import_failed_detail(exc, language=language),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_statement_import_failed_detail(exc, language=language),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_statement_import_failed_detail(exc, language=language),
        ) from exc
    if not result:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=text("statement_text_not_recognized", language),
        )
    response = await _build_import_result_response(
        service,
        payload.telegram_user_id,
        result,
        language=language,
    )
    await session.commit()
    return response


@router.post("/import-file", response_model=StatementImportResultRead)
async def import_statement_file(
    telegram_user_id: int = Form(...),
    telegram_chat_id: int = Form(...),
    language: str | None = Form(None),
    file: UploadFile = File(...),
    actor: ActorContext = Depends(
        require_workspace_roles(
            WorkspaceRole.OWNER,
            WorkspaceRole.CFO,
            WorkspaceRole.COO,
            WorkspaceRole.CASHIER,
        )
    ),
    session: AsyncSession = Depends(get_session),
) -> StatementImportResultRead:
    normalized_language = normalize_language(language, default="en")
    ensure_actor_matches_identity(
        actor,
        telegram_user_id=telegram_user_id,
        telegram_chat_id=telegram_chat_id,
    )
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=text("statement_file_required", normalized_language),
        )

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_STATEMENT_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=text("statement_file_type_unsupported", normalized_language),
        )

    settings = get_settings()
    upload_dir = Path(settings.local_storage_path) / "imports" / "webapp" / "statements"
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination = upload_dir / f"{telegram_user_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}{suffix}"

    contents = await file.read()
    if not contents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=text("statement_file_empty", normalized_language),
        )
    destination.write_bytes(contents)

    service = StatementImportService(session)
    try:
        result = await service.import_file(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            file_path=destination,
            original_filename=file.filename,
            language=normalized_language,
        )
        await session.commit()
    except ActiveStatementImportConflictError as exc:
        _cleanup_uploaded_statement(destination)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_statement_import_blocked_detail(exc, language=normalized_language),
        ) from exc
    except RuntimeError as exc:
        _cleanup_uploaded_statement(destination)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_statement_import_failed_detail(exc, language=normalized_language),
        ) from exc
    except ValueError as exc:
        _cleanup_uploaded_statement(destination)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_statement_import_failed_detail(exc, language=normalized_language),
        ) from exc
    except Exception as exc:
        _cleanup_uploaded_statement(destination)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_statement_import_failed_detail(exc, language=normalized_language),
        ) from exc

    response = await _build_import_result_response(
        service,
        telegram_user_id,
        result,
        language=normalized_language,
    )
    return response


@router.post("/clarify", response_model=StatementClarificationResponse)
async def clarify_statement_item(
    payload: StatementClarificationPayload,
    actor: ActorContext = Depends(
        require_workspace_roles(
            WorkspaceRole.OWNER,
            WorkspaceRole.CFO,
            WorkspaceRole.COO,
            WorkspaceRole.CASHIER,
        )
    ),
    session: AsyncSession = Depends(get_session),
) -> StatementClarificationResponse:
    ensure_actor_matches_identity(
        actor,
        telegram_user_id=payload.telegram_user_id,
        telegram_chat_id=payload.telegram_chat_id,
    )
    service = StatementImportService(session)
    language = normalize_language(payload.language, default="en")
    if payload.account_type and payload.life_sector:
        message = await _run_statement_clarification(
            service.process_clarification_choice(
                telegram_user_id=payload.telegram_user_id,
                telegram_chat_id=payload.telegram_chat_id,
                account_type=payload.account_type,
                life_sector=payload.life_sector,
                language=language,
            ),
            language=language,
        )
    elif payload.answer_text:
        message = await _run_statement_clarification(
            service.process_clarification_text(
                telegram_user_id=payload.telegram_user_id,
                telegram_chat_id=payload.telegram_chat_id,
                answer_text=payload.answer_text,
                language=language,
            ),
            language=language,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=text("statement_clarification_payload_invalid", language),
        )

    if not message:
        fallback_response = await _build_stale_clarification_response(
            service,
            payload.telegram_user_id,
            language=language,
        )
        if fallback_response is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=text("statement_no_pending_for_user", language),
            )
        return fallback_response

    pending = await _build_pending_response(service, payload.telegram_user_id, language=language)
    latest_status = await service.get_latest_status(payload.telegram_user_id)
    history = await service.get_recent_history(payload.telegram_user_id, limit=6)
    await session.commit()
    return StatementClarificationResponse(
        message=message,
        pending=pending,
        latest_status=_build_status_snapshot_response(latest_status),
        history=[_build_history_entry_response(item) for item in history],
    )


async def _build_stale_clarification_response(
    service: StatementImportService,
    telegram_user_id: int,
    *,
    language: str = "en",
) -> StatementClarificationResponse | None:
    pending = await _build_pending_response(service, telegram_user_id, language=language)
    latest_status = await service.get_latest_status(telegram_user_id)
    if not latest_status:
        return None

    history = await service.get_recent_history(telegram_user_id, limit=6)
    message_key = "refreshed_active_clarification" if pending else "loaded_latest_statement_status"
    return StatementClarificationResponse(
        message=text(message_key, language),
        pending=pending,
        latest_status=_build_status_snapshot_response(latest_status),
        history=[_build_history_entry_response(item) for item in history],
    )


async def _build_pending_response(
    service: StatementImportService,
    telegram_user_id: int,
    *,
    language: str = "en",
) -> PendingStatementRead | None:
    pending = await service.get_pending_clarification(telegram_user_id)
    if not pending:
        return None

    prompt_message = await service.get_pending_prompt(telegram_user_id, language=language)
    items = [
        _build_pending_item_response(item)
        for item in pending.get("items", [])
    ]
    current_index = int(pending.get("current_index", 0))
    total_count = len(items)
    resolved_count = min(current_index, total_count)
    remaining_count = max(total_count - current_index, 0)
    current_item = items[current_index] if 0 <= current_index < total_count else None
    return PendingStatementRead(
        statement_id=int(pending["statement_id"]),
        parsed_count=int(pending["parsed_count"]),
        auto_count=int(pending["auto_count"]),
        current_index=current_index,
        total_count=total_count,
        resolved_count=resolved_count,
        remaining_count=remaining_count,
        prompt_message=prompt_message or "",
        current_item=current_item,
        items=items,
    )


async def _build_import_result_response(
    service: StatementImportService,
    telegram_user_id: int,
    result,
    *,
    language: str = "en",
) -> StatementImportResultRead:
    workbench = await _build_workbench_response(
        service,
        telegram_user_id,
        language=language,
        history_limit=6,
    )
    return StatementImportResultRead(
        imported_statement_id=result.imported_statement_id,
        parsed_count=result.parsed_count,
        auto_count=result.auto_count,
        unclear_count=result.unclear_count,
        summary_message=result.summary_message,
        prompt_message=result.prompt_message,
        pending=workbench.pending,
        latest_status=workbench.latest_status,
        history=workbench.history,
    )


async def _build_workbench_response(
    service: StatementImportService,
    telegram_user_id: int,
    *,
    language: str = "en",
    history_limit: int = 6,
) -> StatementWorkbenchRead:
    pending = await _build_pending_response(service, telegram_user_id, language=language)
    latest_status = await service.get_latest_status(telegram_user_id)
    history = await service.get_recent_history(telegram_user_id, limit=history_limit)
    return StatementWorkbenchRead(
        latest_status=_build_status_snapshot_response(latest_status),
        pending=pending,
        history=[_build_history_entry_response(item) for item in history],
    )


def _build_status_snapshot_response(latest_status) -> StatementStatusSnapshotRead | None:
    if not latest_status:
        return None

    return StatementStatusSnapshotRead(
        imported_statement_id=latest_status.imported_statement_id,
        source_name=latest_status.source_name,
        original_filename=latest_status.original_filename,
        parse_status=latest_status.parse_status,
        imported_at=latest_status.imported_at,
        parsed_count=latest_status.parsed_count,
        auto_count=latest_status.auto_count,
        unclear_count=latest_status.unclear_count,
        remaining_clarifications=latest_status.remaining_clarifications,
    )


def _build_history_entry_response(item) -> StatementHistoryEntryRead:
    return StatementHistoryEntryRead(
        imported_statement_id=item.imported_statement_id,
        source_name=item.source_name,
        original_filename=item.original_filename,
        parse_status=item.parse_status,
        imported_at=item.imported_at,
        parsed_count=item.parsed_count,
        auto_count=item.auto_count,
        unclear_count=item.unclear_count,
        remaining_clarifications=item.remaining_clarifications,
    )


def _build_statement_detail_response(detail, *, pending: PendingStatementRead | None) -> StatementDetailRead:
    return StatementDetailRead(
        imported_statement_id=detail.imported_statement_id,
        source_name=detail.source_name,
        original_filename=detail.original_filename,
        parse_status=detail.parse_status,
        imported_at=detail.imported_at,
        parsed_count=detail.parsed_count,
        auto_count=detail.auto_count,
        unclear_count=detail.unclear_count,
        remaining_clarifications=detail.remaining_clarifications,
        note=detail.note,
        storage_kind=detail.storage_kind,
        file_available=detail.file_available,
        is_active=detail.is_active,
        raw_line_count=detail.raw_line_count,
        raw_preview=detail.raw_preview,
        raw_preview_truncated=detail.raw_preview_truncated,
        pending=pending,
    )


def _build_pending_item_response(item: dict) -> PendingStatementItemRead:
    return PendingStatementItemRead(
        index=int(item["index"]),
        statement_date=str(item["statement_date"]),
        amount=item["amount"],
        transaction_type=str(item["transaction_type"]),
        counterparty=str(item["counterparty"]),
        description=str(item["description"]),
        reason=str(item["reason"]),
        suggested_account_type=str(item["suggested_account_type"]) if item.get("suggested_account_type") else None,
        suggested_life_sector=str(item["suggested_life_sector"]) if item.get("suggested_life_sector") else None,
        matched_rules=[
            MatchedClarificationRuleRead(
                match_key=str(rule.get("match_key") or ""),
                account_type=str(rule.get("account_type") or ""),
                life_sector=str(rule.get("life_sector") or ""),
                explanation=str(rule.get("explanation") or ""),
            )
            for rule in item.get("matched_rules", [])
        ],
    )


def _cleanup_uploaded_statement(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # Preserve the original import error if storage cleanup also fails.
        return
