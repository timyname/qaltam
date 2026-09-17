from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.access import ActorContext, ensure_actor_matches_identity, require_workspace_roles
from backend.app.core.config import get_settings
from backend.app.db.database import get_session
from backend.app.models.enums import WorkspaceRole
from backend.app.schemas.receipt import ReceiptUploadResponse
from backend.app.services.chat_service import ChatService
from backend.app.services.receipt_service import ReceiptService

router = APIRouter(prefix="/api/v1/receipts", tags=["receipts"])


@router.post("/upload", response_model=ReceiptUploadResponse)
async def upload_receipt(
    telegram_user_id: int = Form(...),
    telegram_chat_id: int | None = Form(default=None),
    file: UploadFile = File(...),
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
) -> ReceiptUploadResponse:
    ensure_actor_matches_identity(
        actor,
        telegram_user_id=telegram_user_id,
        telegram_chat_id=telegram_chat_id or telegram_user_id,
    )
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Receipt file is required.")

    suffix = Path(file.filename).suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".heic"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported receipt file type. Use JPG, PNG, WEBP, or HEIC.",
        )

    settings = get_settings()
    upload_dir = Path(settings.local_storage_path) / "imports" / "webapp" / "receipts"
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination = upload_dir / f"{telegram_user_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}{suffix}"

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded receipt is empty.")
    destination.write_bytes(contents)

    service = ChatService(session)
    try:
        reply = await service.process_receipt_upload(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id or telegram_user_id,
            image_path=destination,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    if not reply:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Receipt OCR could not detect a valid supermarket receipt.",
        )

    receipt_service = ReceiptService(session)
    receipt = await receipt_service.get_latest_receipt(telegram_user_id=telegram_user_id)
    return ReceiptUploadResponse(message=reply, receipt=receipt)
