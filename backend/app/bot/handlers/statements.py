from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.bot.webapp import build_webapp_url
from backend.app.core.config import get_settings
from backend.app.localization import (
    SUPPORTED_LANGUAGES,
    account_type_label,
    life_sector_label,
    normalize_language,
    resolve_user_language,
    statement_status_label,
    text,
)
from backend.app.services.life_sectors import CLARIFICATION_BUTTON_CHOICES
from backend.app.services.speech_adapter import SpeechAdapter
from backend.app.services.statement_clarification import (
    CLARIFICATION_STOP_WORDS,
    match_statement_clarification_choice,
    ordered_statement_clarification_choices,
)
from backend.app.services.statement_import_service import (
    ActiveStatementImportConflictError,
    StatementDetailSnapshot,
    StatementHistorySnapshot,
    StatementImportService,
    StatementStatusSnapshot,
)
from backend.app.services.statement_parser import StatementParser
from backend.app.services.transaction_parser import TextTransactionParser


SUPPORTED_STATEMENT_EXTENSIONS = {".pdf", ".csv", ".xlsx", ".xls"}
STATEMENT_ROW_DATE_PATTERN = re.compile(r"^(?:\d{2}[./-]\d{2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2})\b")
def _cleanup_downloaded_statement(file_path: Path) -> None:
    try:
        if file_path.exists():
            file_path.unlink()
    except OSError:
        return


def _statement_upload_destination(*, media_dir: Path, file_id: str, suffix: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    return media_dir / f"{file_id}_{timestamp}{suffix}"


def build_statement_router(session_factory: async_sessionmaker) -> Router:
    router = Router()

    @router.message(Command("statement"))
    async def statement_help_handler(message: Message) -> None:
        if not message.from_user:
            return
        async with session_factory() as session:
            lang = await resolve_user_language(
                session,
                telegram_user_id=message.from_user.id,
                fallback_language_code=getattr(message.from_user, "language_code", None),
            )
            service = StatementImportService(session)
            reply_text, pending = await build_statement_status_reply(service, message.from_user.id, lang=lang)
        await message.answer(
            reply_text,
            reply_markup=_clarification_markup(
                _current_pending_item(pending),
                lang=lang,
                statement_id=_pending_statement_id(pending),
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
            )
            if pending
            else _statement_status_markup(
                statement_id=None,
                lang=lang,
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
            ),
        )

    @router.message(Command("clarify"))
    async def clarification_status_handler(message: Message) -> None:
        if not message.from_user:
            return
        async with session_factory() as session:
            lang = await resolve_user_language(
                session,
                telegram_user_id=message.from_user.id,
                fallback_language_code=getattr(message.from_user, "language_code", None),
            )
            service = StatementImportService(session)
            pending = await service.get_pending_clarification(message.from_user.id)
            prompt = await service.get_pending_prompt(message.from_user.id, language=lang)
            latest_status = await service.get_latest_status(message.from_user.id)
        if not pending or not prompt:
            await message.answer(
                _no_pending_clarification_text(latest_status, lang=lang),
                reply_markup=_statement_status_markup(
                    statement_id=latest_status.imported_statement_id if latest_status else None,
                    source_statement_id=latest_status.imported_statement_id if latest_status else None,
                    lang=lang,
                    telegram_user_id=message.from_user.id,
                    telegram_chat_id=message.chat.id,
                ),
            )
            return
        await message.answer(
            _pending_status_text(pending_prompt=prompt, latest_status=latest_status, pending=pending, lang=lang),
            reply_markup=_clarification_markup(
                _current_pending_item(pending),
                lang=lang,
                statement_id=_pending_statement_id(pending),
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
            ),
        )

    @router.message(F.document)
    async def statement_document_handler(message: Message) -> None:
        await handle_statement_document(session_factory, message)

    @router.callback_query(F.data.startswith("stmt:"))
    async def statement_callback_handler(callback: CallbackQuery) -> None:
        if not callback.from_user or not callback.message or not callback.data:
            return
        lang = normalize_language(getattr(callback.from_user, "language_code", None), default="ru")
        try:
            _, account_type, life_sector = callback.data.split(":", maxsplit=2)
        except ValueError:
            await callback.answer(text("invalid_action", lang), show_alert=True)
            return
        if account_type == "status":
            async with session_factory() as session:
                lang = await resolve_user_language(
                    session,
                    telegram_user_id=callback.from_user.id,
                    fallback_language_code=getattr(callback.from_user, "language_code", None),
                )
                service = StatementImportService(session)
                if life_sector.startswith("source-"):
                    statement_id = _parse_statement_source_action(life_sector)
                    if statement_id is None:
                        await callback.answer(text("invalid_action", lang), show_alert=True)
                        return
                    try:
                        callback_notice, show_alert = await _send_statement_source_message(
                            callback.message,
                            service,
                            telegram_user_id=callback.from_user.id,
                            statement_id=statement_id,
                            lang=lang,
                        )
                    except Exception as exc:
                        await callback.answer(text("statement_source_send_failed", lang, details=exc), show_alert=True)
                        return
                    await callback.answer(callback_notice, show_alert=show_alert)
                    return
                reply_text, reply_markup, callback_notice, show_alert = await build_statement_callback_reply(
                    service,
                    telegram_user_id=callback.from_user.id,
                    telegram_chat_id=callback.message.chat.id,
                    action=life_sector,
                    lang=lang,
                )
            await callback.answer(callback_notice, show_alert=show_alert)
            await _refresh_callback_message(callback, reply_text, reply_markup=reply_markup)
            return
        if account_type == "refresh" and life_sector == "status":
            async with session_factory() as session:
                lang = await resolve_user_language(
                    session,
                    telegram_user_id=callback.from_user.id,
                    fallback_language_code=getattr(callback.from_user, "language_code", None),
                )
                service = StatementImportService(session)
                reply_text, reply_markup, callback_notice, show_alert = await build_statement_callback_reply(
                    service,
                    telegram_user_id=callback.from_user.id,
                    telegram_chat_id=callback.message.chat.id,
                    action="resume",
                    lang=lang,
                )
            await callback.answer(callback_notice, show_alert=show_alert)
            await _refresh_callback_message(callback, reply_text, reply_markup=reply_markup)
            return

        async with session_factory() as session:
            lang = await resolve_user_language(
                session,
                telegram_user_id=callback.from_user.id,
                fallback_language_code=getattr(callback.from_user, "language_code", None),
            )
            service = StatementImportService(session)
            try:
                reply = await service.process_clarification_choice(
                    telegram_user_id=callback.from_user.id,
                    telegram_chat_id=callback.message.chat.id,
                    account_type=account_type,
                    life_sector=life_sector,
                    language=lang,
                )
            except Exception as exc:
                await callback.answer(text("statement_clarification_failed", lang, details=exc), show_alert=True)
                return
            pending = await service.get_pending_clarification(callback.from_user.id)
            latest_status = await service.get_latest_status(callback.from_user.id)
            await session.commit()

        if not reply:
            async with session_factory() as session:
                service = StatementImportService(session)
                reply_text, reply_markup, callback_notice, show_alert = await build_statement_callback_reply(
                    service,
                    telegram_user_id=callback.from_user.id,
                    telegram_chat_id=callback.message.chat.id,
                    action="resume",
                    lang=lang,
                )
            await callback.answer(callback_notice, show_alert=show_alert)
            await _refresh_callback_message(callback, reply_text, reply_markup=reply_markup)
            return

        await callback.answer(text("saved", lang))
        if reply:
                await _refresh_callback_message(
                    callback,
                    _completed_statement_text(reply, latest_status, lang=lang) if not pending else reply,
                    reply_markup=_clarification_markup(
                        _current_pending_item(pending),
                        lang=lang,
                        statement_id=_pending_statement_id(pending),
                        telegram_user_id=callback.from_user.id,
                        telegram_chat_id=callback.message.chat.id,
                    )
                    if pending
                    else _statement_status_markup(
                        statement_id=latest_status.imported_statement_id if latest_status else None,
                        source_statement_id=latest_status.imported_statement_id if latest_status else None,
                        lang=lang,
                        telegram_user_id=callback.from_user.id,
                        telegram_chat_id=callback.message.chat.id,
                    ),
                )

    return router


async def try_handle_statement_text(session_factory: async_sessionmaker, message: Message) -> bool:
    if not message.from_user or not message.text:
        return False

    async with session_factory() as session:
        lang = await resolve_user_language(
            session,
            telegram_user_id=message.from_user.id,
            fallback_language_code=getattr(message.from_user, "language_code", None),
        )
        service = StatementImportService(session)
        pending = await service.get_pending_clarification(message.from_user.id)
        if await _handle_statement_message_shortcut(
            service,
            message,
            telegram_user_id=message.from_user.id,
            telegram_chat_id=message.chat.id,
            value=message.text,
            lang=lang,
        ):
            return True
        if pending and StatementParser.looks_like_statement_text(message.text):
            prompt = await service.get_pending_prompt(message.from_user.id, language=lang)
            latest_status = await service.get_latest_status(message.from_user.id)
            await message.answer(
                _statement_import_blocked_text(latest_status, pending=pending, lang=lang)
            )
            if prompt:
                await message.answer(
                    _pending_status_text(pending_prompt=prompt, latest_status=latest_status, pending=pending, lang=lang),
                    reply_markup=_clarification_markup(
                        _current_pending_item(pending),
                        lang=lang,
                        statement_id=_pending_statement_id(pending),
                        telegram_user_id=message.from_user.id,
                        telegram_chat_id=message.chat.id,
                    ),
                )
            return True
        if pending and _looks_like_transaction_log(message.text):
            return False
        if pending and not _looks_like_clarification_answer(message.text, pending=pending, lang=lang):
            return False

        try:
            reply = await service.process_clarification_text(
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
                answer_text=message.text,
                language=lang,
            )
        except Exception as exc:
            await message.answer(text("statement_clarification_failed", lang, details=exc))
            return True
        if pending and not reply:
            latest_status = await service.get_latest_status(message.from_user.id)
            await message.answer(
                _no_pending_clarification_text(latest_status, lang=lang),
                reply_markup=_statement_status_markup(
                    statement_id=latest_status.imported_statement_id if latest_status else None,
                    source_statement_id=latest_status.imported_statement_id if latest_status else None,
                    lang=lang,
                    telegram_user_id=message.from_user.id,
                    telegram_chat_id=message.chat.id,
                ),
            )
            return True
        if reply:
            pending = await service.get_pending_clarification(message.from_user.id)
            latest_status = await service.get_latest_status(message.from_user.id)
            await session.commit()
            await message.answer(
                _completed_statement_text(reply, latest_status, lang=lang) if not pending else reply,
                reply_markup=_clarification_markup(
                    _current_pending_item(pending),
                    lang=lang,
                    statement_id=_pending_statement_id(pending),
                    telegram_user_id=message.from_user.id,
                    telegram_chat_id=message.chat.id,
                )
                if pending
                else _statement_status_markup(
                    statement_id=latest_status.imported_statement_id if latest_status else None,
                    source_statement_id=latest_status.imported_statement_id if latest_status else None,
                    lang=lang,
                    telegram_user_id=message.from_user.id,
                    telegram_chat_id=message.chat.id,
                ),
            )
            return True

        try:
            result = await service.import_text(
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
                raw_text=message.text,
                language=lang,
            )
        except ActiveStatementImportConflictError:
            pending = await service.get_pending_clarification(message.from_user.id)
            prompt = await service.get_pending_prompt(message.from_user.id, language=lang)
            latest_status = await service.get_latest_status(message.from_user.id)
            await message.answer(_statement_import_blocked_text(latest_status, pending=pending, lang=lang))
            if prompt:
                await message.answer(
                    _pending_status_text(
                        pending_prompt=prompt,
                        latest_status=latest_status,
                        pending=pending,
                        lang=lang,
                    ),
                    reply_markup=_clarification_markup(
                        _current_pending_item(pending),
                        lang=lang,
                        statement_id=_pending_statement_id(pending),
                        telegram_user_id=message.from_user.id,
                        telegram_chat_id=message.chat.id,
                    ),
                )
            return True
        except Exception as exc:
            await message.answer(text("statement_import_failed", lang, details=exc))
            return True
        if not result:
            return False

        pending = await service.get_pending_clarification(message.from_user.id)
        latest_status = await service.get_latest_status(message.from_user.id)
        await session.commit()

    await message.answer(result.summary_message)
    if result.prompt_message:
        await message.answer(
            result.prompt_message,
            reply_markup=_clarification_markup(
                _current_pending_item(pending),
                lang=lang,
                statement_id=_pending_statement_id(pending),
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
            )
            if pending
            else None,
        )
    else:
        await message.answer(
            _latest_statement_text(latest_status, lang=lang) if latest_status else _statement_help_text(lang=lang),
            reply_markup=_statement_status_markup(
                statement_id=latest_status.imported_statement_id if latest_status else None,
                source_statement_id=latest_status.imported_statement_id if latest_status else None,
                lang=lang,
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
            ),
        )
    return True


async def handle_statement_document(session_factory: async_sessionmaker, message: Message) -> bool:
    if not message.from_user or not message.document or not message.document.file_name:
        return False

    suffix = Path(message.document.file_name).suffix.lower()
    if suffix not in SUPPORTED_STATEMENT_EXTENSIONS:
        lang = normalize_language(getattr(message.from_user, "language_code", None), default="ru")
        await message.answer(
            text("unsupported_statement_document", lang)
        )
        return True

    settings = get_settings()
    media_dir = Path(settings.local_storage_path) / "imports" / "telegram" / "statements"
    media_dir.mkdir(parents=True, exist_ok=True)
    destination = _statement_upload_destination(
        media_dir=media_dir,
        file_id=message.document.file_id,
        suffix=suffix,
    )
    await message.bot.download(message.document.file_id, destination=destination)

    try:
        async with session_factory() as session:
            lang = await resolve_user_language(
                session,
                telegram_user_id=message.from_user.id,
                fallback_language_code=getattr(message.from_user, "language_code", None),
            )
            service = StatementImportService(session)
            result = await service.import_file(
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
                file_path=destination,
                original_filename=message.document.file_name,
                language=lang,
            )
            pending = await service.get_pending_clarification(message.from_user.id)
            latest_status = await service.get_latest_status(message.from_user.id)
            await session.commit()
    except ActiveStatementImportConflictError:
        _cleanup_downloaded_statement(destination)
        async with session_factory() as session:
            lang = await resolve_user_language(
                session,
                telegram_user_id=message.from_user.id,
                fallback_language_code=getattr(message.from_user, "language_code", None),
            )
            service = StatementImportService(session)
            pending = await service.get_pending_clarification(message.from_user.id)
            prompt = await service.get_pending_prompt(message.from_user.id, language=lang)
            latest_status = await service.get_latest_status(message.from_user.id)
        await message.answer(_statement_import_blocked_text(latest_status, pending=pending, lang=lang))
        if prompt:
            await message.answer(
                _pending_status_text(pending_prompt=prompt, latest_status=latest_status, pending=pending, lang=lang),
                reply_markup=_clarification_markup(
                    _current_pending_item(pending),
                    lang=lang,
                    statement_id=_pending_statement_id(pending),
                    telegram_user_id=message.from_user.id,
                    telegram_chat_id=message.chat.id,
                ),
            )
        return True
    except Exception as exc:
        _cleanup_downloaded_statement(destination)
        lang = normalize_language(getattr(message.from_user, "language_code", None), default="ru")
        await message.answer(
            text("statement_import_failed", lang, details=exc)
        )
        return True

    await message.answer(result.summary_message)
    if result.prompt_message:
        await message.answer(
            result.prompt_message,
            reply_markup=_clarification_markup(
                _current_pending_item(pending),
                lang=lang,
                statement_id=_pending_statement_id(pending),
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
            )
            if pending
            else None,
        )
    else:
        await message.answer(
            _latest_statement_text(latest_status, lang=lang) if latest_status else _statement_help_text(lang=lang),
            reply_markup=_statement_status_markup(
                statement_id=latest_status.imported_statement_id if latest_status else None,
                source_statement_id=latest_status.imported_statement_id if latest_status else None,
                lang=lang,
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
            ),
        )
    return True


async def try_handle_statement_voice(
    session_factory: async_sessionmaker,
    message: Message,
    audio_path: Path,
) -> bool:
    if not message.from_user:
        return False

    async with session_factory() as session:
        lang = await resolve_user_language(
            session,
            telegram_user_id=message.from_user.id,
            fallback_language_code=getattr(message.from_user, "language_code", None),
        )
        service = StatementImportService(session)
        pending = await service.get_pending_clarification(message.from_user.id)

    try:
        transcript = SpeechAdapter().transcribe(audio_path)
    except Exception as exc:
        await message.answer(
            text("voice_clarification_unavailable", lang, details=exc)
        )
        return True

    if _looks_like_transaction_log(transcript):
        return False
    async with session_factory() as session:
        service = StatementImportService(session)
        if await _handle_statement_message_shortcut(
            service,
            message,
            telegram_user_id=message.from_user.id,
            telegram_chat_id=message.chat.id,
            value=transcript,
            lang=lang,
        ):
            return True
    if not pending or not _looks_like_clarification_answer(transcript, pending=pending, lang=lang):
        return False

    async with session_factory() as session:
        service = StatementImportService(session)
        try:
            reply = await service.process_clarification_text(
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
                answer_text=transcript,
                language=lang,
            )
        except Exception as exc:
            await message.answer(text("statement_clarification_failed", lang, details=exc))
            return True
        if not reply:
            latest_status = await service.get_latest_status(message.from_user.id)
            await message.answer(
                _no_pending_clarification_text(latest_status, lang=lang),
                reply_markup=_statement_status_markup(
                    statement_id=latest_status.imported_statement_id if latest_status else None,
                    source_statement_id=latest_status.imported_statement_id if latest_status else None,
                    lang=lang,
                    telegram_user_id=message.from_user.id,
                    telegram_chat_id=message.chat.id,
                ),
            )
            return True
        pending = await service.get_pending_clarification(message.from_user.id)
        latest_status = await service.get_latest_status(message.from_user.id)
        await session.commit()

    await message.answer(
        _completed_statement_text(reply, latest_status, lang=lang) if not pending else reply,
        reply_markup=_clarification_markup(
            _current_pending_item(pending),
            lang=lang,
            statement_id=_pending_statement_id(pending),
            telegram_user_id=message.from_user.id,
            telegram_chat_id=message.chat.id,
        )
        if pending
        else _statement_status_markup(
            statement_id=latest_status.imported_statement_id if latest_status else None,
            source_statement_id=latest_status.imported_statement_id if latest_status else None,
            lang=lang,
            telegram_user_id=message.from_user.id,
            telegram_chat_id=message.chat.id,
        ),
    )
    return True


async def build_statement_status_reply(
    service: StatementImportService,
    telegram_user_id: int,
    *,
    lang: str = "en",
) -> tuple[str, dict | None]:
    pending = await service.get_pending_clarification(telegram_user_id)
    prompt = await service.get_pending_prompt(telegram_user_id, language=lang) if pending else None
    latest_status = await service.get_latest_status(telegram_user_id)
    if pending and prompt:
        return _pending_status_text(pending_prompt=prompt, latest_status=latest_status, pending=pending, lang=lang), pending
    if latest_status:
        return _latest_statement_text(latest_status, lang=lang), None
    return _statement_help_text(lang=lang), None


async def _handle_statement_message_shortcut(
    service: StatementImportService,
    message: Message,
    *,
    telegram_user_id: int,
    telegram_chat_id: int | None = None,
    value: str,
    lang: str = "en",
) -> bool:
    shortcut = await _resolve_statement_message_shortcut(
        service,
        telegram_user_id=telegram_user_id,
        value=value,
        lang=lang,
    )
    if not shortcut:
        return False

    kind, payload = shortcut
    if kind == "callback":
        reply_text, reply_markup, _callback_notice, _show_alert = await build_statement_callback_reply(
            service,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            action=str(payload),
            lang=lang,
        )
        await message.answer(reply_text, reply_markup=reply_markup)
        return True

    if kind == "detail_not_found":
        await message.answer(text("statement_detail_not_found", lang))
        return True

    if kind == "no_statement_imports":
        await message.answer(text("no_statement_imports_yet", lang))
        return True

    try:
        callback_notice, show_alert = await _send_statement_source_message(
            message,
            service,
            telegram_user_id=telegram_user_id,
            statement_id=int(payload),
            lang=lang,
        )
    except Exception as exc:
        await message.answer(text("statement_source_send_failed", lang, details=exc))
        return True

    if show_alert:
        await message.answer(callback_notice)
    return True


async def _resolve_statement_message_shortcut(
    service: StatementImportService,
    *,
    telegram_user_id: int,
    value: str,
    lang: str = "en",
) -> tuple[str, str | int] | None:
    if action := _statement_text_action(value, lang=lang):
        return ("callback", action)

    request = _parse_statement_shortcut_request(value, lang=lang)
    if not request:
        return None

    request_kind, reference = request
    statement_id = await _resolve_statement_shortcut_reference(
        service,
        telegram_user_id=telegram_user_id,
        reference=reference,
        lang=lang,
    )
    if statement_id is None:
        if _is_latest_statement_reference(reference) or _is_current_statement_reference(reference):
            return ("no_statement_imports", reference)
        return ("detail_not_found", reference)

    if request_kind == "detail":
        return ("callback", f"detail-{statement_id}")
    return ("source", statement_id)


async def build_statement_callback_reply(
    service: StatementImportService,
    *,
    telegram_user_id: int,
    telegram_chat_id: int | None = None,
    action: str,
    lang: str = "en",
) -> tuple[str, InlineKeyboardMarkup, str, bool]:
    pending = await service.get_pending_clarification(telegram_user_id)
    prompt = await service.get_pending_prompt(telegram_user_id, language=lang) if pending else None
    latest_status = await service.get_latest_status(telegram_user_id)

    if action == "resume":
        if pending and prompt:
            return (
                _pending_status_text(pending_prompt=prompt, latest_status=latest_status, pending=pending, lang=lang),
                _clarification_markup(
                    _current_pending_item(pending),
                    lang=lang,
                    statement_id=_pending_statement_id(pending),
                    telegram_user_id=telegram_user_id,
                    telegram_chat_id=telegram_chat_id,
                ),
                text("refreshed_active_clarification", lang),
                False,
            )
        return (
            _no_pending_clarification_text(latest_status, lang=lang),
            _statement_status_markup(
                statement_id=latest_status.imported_statement_id if latest_status else None,
                source_statement_id=latest_status.imported_statement_id if latest_status else None,
                lang=lang,
                telegram_user_id=telegram_user_id,
                telegram_chat_id=telegram_chat_id,
            ),
            text("no_pending_statement_clarification_alert", lang),
            True,
        )

    if action == "latest":
        if latest_status:
            return (
                _latest_statement_text(latest_status, lang=lang),
                _statement_status_markup(
                    has_pending=bool(pending and prompt),
                    statement_id=_pending_statement_id(pending) if pending and prompt else latest_status.imported_statement_id,
                    source_statement_id=latest_status.imported_statement_id,
                    lang=lang,
                    telegram_user_id=telegram_user_id,
                    telegram_chat_id=telegram_chat_id,
                ),
                text("loaded_latest_statement_status", lang),
                False,
            )
        return (
            _statement_help_text(lang=lang),
            _statement_status_markup(
                statement_id=None,
                lang=lang,
                telegram_user_id=telegram_user_id,
                telegram_chat_id=telegram_chat_id,
            ),
            text("no_statement_imports_yet", lang),
            True,
        )

    if action == "history":
        history = await service.get_recent_history(telegram_user_id, limit=5)
        if history:
            return (
                _statement_history_text(history, latest_status=latest_status, lang=lang),
                _statement_history_markup(
                    history,
                    has_pending=bool(pending and prompt),
                    lang=lang,
                    telegram_user_id=telegram_user_id,
                    telegram_chat_id=telegram_chat_id,
                ),
                text("loaded_recent_statement_imports", lang),
                False,
            )
        return (
            _statement_help_text(lang=lang),
            _statement_status_markup(
                has_pending=bool(pending and prompt),
                statement_id=_pending_statement_id(pending) if pending and prompt else latest_status.imported_statement_id if latest_status else None,
                lang=lang,
                telegram_user_id=telegram_user_id,
                telegram_chat_id=telegram_chat_id,
            ),
            text("no_statement_imports_yet", lang),
            True,
        )

    if action.startswith("detail-"):
        statement_id = _parse_statement_detail_action(action)
        if statement_id is None:
            return (
                _statement_help_text(lang=lang),
                _statement_status_markup(
                    has_pending=bool(pending and prompt),
                    statement_id=_pending_statement_id(pending) if pending and prompt else latest_status.imported_statement_id if latest_status else None,
                    lang=lang,
                    telegram_user_id=telegram_user_id,
                    telegram_chat_id=telegram_chat_id,
                ),
                text("invalid_action", lang),
                True,
            )

        detail = await service.get_statement_detail(telegram_user_id, statement_id)
        if detail:
            detail_pending = pending if pending and int(pending.get("statement_id", 0)) == detail.imported_statement_id else None
            return (
                _statement_detail_text(detail, latest_status=latest_status, pending=detail_pending, lang=lang),
                _statement_detail_markup(
                    detail,
                    has_pending=bool(pending and prompt),
                    lang=lang,
                    telegram_user_id=telegram_user_id,
                    telegram_chat_id=telegram_chat_id,
                ),
                text("loaded_statement_import_detail", lang),
                False,
            )

        history = await service.get_recent_history(telegram_user_id, limit=5)
        if history:
            return (
                _statement_history_text(history, latest_status=latest_status, lang=lang),
                _statement_history_markup(
                    history,
                    has_pending=bool(pending and prompt),
                    lang=lang,
                    telegram_user_id=telegram_user_id,
                    telegram_chat_id=telegram_chat_id,
                ),
                text("statement_detail_not_found", lang),
                True,
            )
        return (
            _statement_help_text(lang=lang),
            _statement_status_markup(
                has_pending=bool(pending and prompt),
                statement_id=_pending_statement_id(pending) if pending and prompt else latest_status.imported_statement_id if latest_status else None,
                lang=lang,
                telegram_user_id=telegram_user_id,
                telegram_chat_id=telegram_chat_id,
            ),
            text("statement_detail_not_found", lang),
            True,
        )

    return (
        _statement_help_text(lang=lang),
        _statement_status_markup(
            has_pending=bool(pending and prompt),
            statement_id=_pending_statement_id(pending) if pending and prompt else latest_status.imported_statement_id if latest_status else None,
            lang=lang,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
        ),
        text("unsupported_action", lang),
        True,
    )


async def _refresh_callback_message(
    callback: CallbackQuery,
    reply_text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if not callback.message:
        return

    try:
        await callback.message.edit_text(reply_text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        await callback.message.answer(reply_text, reply_markup=reply_markup)


async def _send_statement_source_message(
    message: Message,
    service: StatementImportService,
    *,
    telegram_user_id: int,
    statement_id: int,
    lang: str = "en",
) -> tuple[str, bool]:
    source = await service.get_statement_source(telegram_user_id, statement_id)
    if not source:
        return text("statement_source_not_available", lang), True

    document = (
        FSInputFile(source.file_path, filename=source.filename)
        if source.file_path
        else BufferedInputFile(source.content or b"", filename=source.filename)
    )
    await message.answer_document(
        document=document,
        caption=text("statement_source_caption", lang, name=source.filename),
    )
    return text("statement_source_sent", lang, name=source.filename), False


def _clarification_markup(
    item: dict | None = None,
    *,
    lang: str = "en",
    statement_id: int | None = None,
    telegram_user_id: int | None = None,
    telegram_chat_id: int | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for choice in ordered_statement_clarification_choices(item, lang=lang):
        builder.button(
            text=choice.label,
            callback_data=f"stmt:{choice.account_type}:{choice.life_sector}",
        )
    builder.button(text=text("refresh_active_statement", lang), callback_data="stmt:status:resume")
    builder.button(text=text("latest_statement_status", lang), callback_data="stmt:status:latest")
    builder.button(text=text("recent_statement_imports", lang), callback_data="stmt:status:history")
    builder.row(
        InlineKeyboardButton(
            text=text("open_app", lang),
            web_app=WebAppInfo(
                url=build_webapp_url(
                    tab="quick",
                    focus="clarify",
                    statement_id=statement_id,
                    telegram_user_id=telegram_user_id,
                    telegram_chat_id=telegram_chat_id,
                )
            ),
        )
    )
    builder.adjust(1, 2, 2, 2, 2, 2, 1)
    return builder.as_markup()


def _statement_help_markup(
    *,
    lang: str = "en",
    telegram_user_id: int | None = None,
    telegram_chat_id: int | None = None,
) -> InlineKeyboardMarkup:
    return _statement_status_markup(
        lang=lang,
        telegram_user_id=telegram_user_id,
        telegram_chat_id=telegram_chat_id,
    )


def _statement_history_markup(
    history: list[StatementHistorySnapshot],
    *,
    has_pending: bool = False,
    lang: str = "en",
    telegram_user_id: int | None = None,
    telegram_chat_id: int | None = None,
) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []
    for index, item in enumerate(history, start=1):
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=_statement_history_button_label(item, index=index),
                    callback_data=f"stmt:status:detail-{item.imported_statement_id}",
                ),
                InlineKeyboardButton(
                    text=text("statement_source_short", lang),
                    callback_data=f"stmt:status:source-{item.imported_statement_id}",
                ),
            ]
        )
    keyboard.extend(
        _statement_navigation_rows(
            has_pending=has_pending,
            include_history=True,
            lang=lang,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
        )
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def _statement_status_markup(
    *,
    has_pending: bool = False,
    statement_id: int | None = None,
    source_statement_id: int | None = None,
    lang: str = "en",
    telegram_user_id: int | None = None,
    telegram_chat_id: int | None = None,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=_statement_navigation_rows(
            has_pending=has_pending,
            include_history=True,
            statement_id=statement_id,
            source_statement_id=source_statement_id,
            lang=lang,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
        )
    )


def _statement_detail_markup(
    detail: StatementDetailSnapshot,
    *,
    has_pending: bool = False,
    lang: str = "en",
    telegram_user_id: int | None = None,
    telegram_chat_id: int | None = None,
) -> InlineKeyboardMarkup:
    focus = "clarify" if has_pending else "statement"
    keyboard: list[list[InlineKeyboardButton]] = []
    if detail.is_active and detail.remaining_clarifications > 0:
        keyboard.append([InlineKeyboardButton(text=text("resume_clarification", lang), callback_data="stmt:status:resume")])
    keyboard.append(
        [
            InlineKeyboardButton(
                text=text("send_statement_source", lang),
                callback_data=f"stmt:status:source-{detail.imported_statement_id}",
            )
        ]
    )
    keyboard.append([InlineKeyboardButton(text=text("back_to_history", lang), callback_data="stmt:status:history")])
    keyboard.append([InlineKeyboardButton(text=text("latest_statement_status", lang), callback_data="stmt:status:latest")])
    keyboard.append(
        [
            InlineKeyboardButton(
                text=text("open_app", lang),
                web_app=WebAppInfo(
                    url=build_webapp_url(
                        tab="quick",
                        focus=focus,
                        statement_id=detail.imported_statement_id,
                        telegram_user_id=telegram_user_id,
                        telegram_chat_id=telegram_chat_id,
                    )
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def _statement_navigation_rows(
    *,
    has_pending: bool = False,
    include_history: bool = True,
    statement_id: int | None = None,
    source_statement_id: int | None = None,
    lang: str = "en",
    telegram_user_id: int | None = None,
    telegram_chat_id: int | None = None,
) -> list[list[InlineKeyboardButton]]:
    focus = "clarify" if has_pending else "statement"
    keyboard: list[list[InlineKeyboardButton]] = []
    if has_pending:
        keyboard.append([InlineKeyboardButton(text=text("resume_clarification", lang), callback_data="stmt:status:resume")])
    keyboard.append([InlineKeyboardButton(text=text("latest_statement_status", lang), callback_data="stmt:status:latest")])
    if source_statement_id is not None:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=text("send_statement_source", lang),
                    callback_data=f"stmt:status:source-{source_statement_id}",
                )
            ]
        )
    if include_history:
        keyboard.append([InlineKeyboardButton(text=text("recent_statement_imports", lang), callback_data="stmt:status:history")])
    keyboard.append(
        [
            InlineKeyboardButton(
                text=text("open_app", lang),
                web_app=WebAppInfo(
                    url=build_webapp_url(
                        tab="quick",
                        focus=focus,
                        statement_id=statement_id,
                        telegram_user_id=telegram_user_id,
                        telegram_chat_id=telegram_chat_id,
                    )
                ),
            )
        ]
    )
    return keyboard


def _statement_help_text(*, lang: str = "en") -> str:
    return "\n".join([text("help_line_1", lang), text("help_line_2", lang), text("help_line_3", lang)])


def _statement_text_action(value: str, *, lang: str = "en") -> str | None:
    normalized = _normalize_statement_action(value)
    if not normalized:
        return None

    action_aliases = {
        "resume": {
            "clarify",
            "resume",
            "resume clarification",
            "refresh",
            "refresh active statement",
            "active clarification",
            "continue clarification",
        },
        "latest": {
            "statement",
            "statement status",
            "status",
            "latest",
            "latest status",
            "latest statement",
            "latest statement status",
        },
        "history": {
            "history",
            "statement history",
            "recent imports",
            "recent statements",
            "recent statement imports",
            "imports",
        },
    }

    languages = {normalize_language(lang), *SUPPORTED_LANGUAGES}
    for language in languages:
        action_aliases["resume"].update(
            {
                _normalize_statement_action(text("resume_clarification", language)),
                _normalize_statement_action(text("refresh_active_statement", language)),
                _normalize_statement_action(text("refreshed_active_clarification", language)),
            }
        )
        action_aliases["latest"].update({_normalize_statement_action(text("latest_statement_status", language))})
        action_aliases["history"].update(
            {
                _normalize_statement_action(text("recent_statement_imports", language)),
                _normalize_statement_action(text("recent_statement_imports_title", language)),
            }
        )

    for action, aliases in action_aliases.items():
        if normalized in aliases:
            return action
    return None


def _parse_statement_shortcut_request(value: str, *, lang: str = "en") -> tuple[str, str] | None:
    normalized = _normalize_statement_action(value)
    if not normalized:
        return None

    for phrase in _statement_shortcut_phrases(normalized, lang=lang):
        for prefix in sorted(_statement_source_prefixes(lang=lang), key=len, reverse=True):
            if phrase == prefix:
                return ("source", "current")
            if phrase.startswith(f"{prefix} "):
                reference = _statement_shortcut_reference_value(phrase[len(prefix) :].strip(), lang=lang)
                if reference:
                    return ("source", reference)
            if phrase.endswith(f" {prefix}"):
                reference = _statement_shortcut_reference_value(phrase[: -len(prefix)].strip(), lang=lang)
                if reference:
                    return ("source", reference)

        for prefix in sorted(_statement_detail_prefixes(lang=lang), key=len, reverse=True):
            if phrase.startswith(f"{prefix} "):
                reference = _statement_shortcut_reference_value(phrase[len(prefix) :].strip(), lang=lang)
                if reference:
                    return ("detail", reference)
            if phrase.endswith(f" {prefix}"):
                reference = _statement_shortcut_reference_value(phrase[: -len(prefix)].strip(), lang=lang)
                if reference:
                    return ("detail", reference)

    return None


async def _resolve_statement_shortcut_reference(
    service: StatementImportService,
    *,
    telegram_user_id: int,
    reference: str,
    lang: str = "en",
) -> int | None:
    normalized_reference = _normalize_statement_action(reference)
    if not normalized_reference:
        return None

    pending = await service.get_pending_clarification(telegram_user_id)
    latest_status = await service.get_latest_status(telegram_user_id)
    history: list[StatementHistorySnapshot] | None = None

    for candidate in _statement_reference_candidates(normalized_reference, lang=lang):
        if _is_current_statement_reference(candidate, lang=lang):
            pending_statement_id = _pending_statement_id(pending)
            if pending_statement_id is not None:
                return pending_statement_id
            return latest_status.imported_statement_id if latest_status else None

        if _is_latest_statement_reference(candidate, lang=lang):
            return latest_status.imported_statement_id if latest_status else _pending_statement_id(pending)

        history_index = _statement_history_index_from_reference(candidate)
        if history_index is not None:
            if history is None:
                history = await service.get_recent_history(telegram_user_id, limit=5)
            if 1 <= history_index <= len(history):
                return history[history_index - 1].imported_statement_id
            return None

    return None


def _statement_detail_prefixes(*, lang: str = "en") -> set[str]:
    languages = {normalize_language(lang), *SUPPORTED_LANGUAGES}
    prefixes = {
        "detail",
        "details",
        "import detail",
        "import details",
        "open",
        "show",
        "statement",
        "statement detail",
        "history",
        "import",
        "statement import detail",
    }
    for language in languages:
        prefixes.update(
            {
                _normalize_statement_action(text("recent_statement_imports", language)),
                _normalize_statement_action(text("recent_statement_imports_title", language)),
            }
        )
    prefixes.update(
        {
            "детали",
            "детально",
            "показать",
            "открыть",
            "выписка",
            "импорт",
            "ашу",
            "корсету",
            "узинди",
            "деталі",
            "відкрити",
            "показати",
            "виписка",
            "імпорт",
        }
    )
    prefixes.discard("")
    return prefixes


def _statement_shortcut_phrases(value: str, *, lang: str = "en") -> list[str]:
    normalized = _normalize_statement_action(value)
    if not normalized:
        return []

    phrases = [normalized]
    trimmed = " ".join(
        token for token in normalized.split() if token not in _statement_shortcut_noise_tokens(lang=lang)
    ).strip()
    if trimmed and trimmed not in phrases:
        phrases.append(trimmed)
    return phrases


def _statement_shortcut_noise_tokens(*, lang: str = "en") -> set[str]:
    del lang
    return {
        "a",
        "an",
        "for",
        "from",
        "me",
        "my",
        "now",
        "please",
        "pls",
        "plz",
        "the",
        "пж",
        "пожалуйста",
        "будь",
        "ласка",
        "өтінемін",
        "отинемин",
    }


def _statement_source_prefixes(*, lang: str = "en") -> set[str]:
    languages = {normalize_language(lang), *SUPPORTED_LANGUAGES}
    prefixes = {
        "source",
        "source file",
        "send source",
        "send source file",
        "file",
        "statement source",
        "original file",
        "download source",
        "download file",
    }
    for language in languages:
        prefixes.update(
            {
                _normalize_statement_action(text("send_statement_source", language)),
                _normalize_statement_action(text("statement_source_short", language)),
            }
        )
    prefixes.update(
        {
            "исходник",
            "источник",
            "прислать исходник",
            "дереккоз",
            "дереккоз файлын жиберу",
            "файлды жиберу",
            "джерело",
            "надіслати джерело",
        }
    )
    prefixes.discard("")
    return prefixes


def _statement_history_index_from_reference(reference: str) -> int | None:
    normalized_reference = _normalize_statement_action(reference)
    if not normalized_reference:
        return None

    matches: set[int] = set()
    direct_match = re.fullmatch(r"(\d+)(?:st|nd|rd|th)", normalized_reference)
    if normalized_reference.isdigit():
        matches.add(int(normalized_reference))
    elif direct_match:
        matches.add(int(direct_match.group(1)))

    ordinal_aliases = _statement_history_reference_aliases()
    if normalized_reference in ordinal_aliases:
        matches.add(ordinal_aliases[normalized_reference])

    for token in normalized_reference.split():
        if token.isdigit():
            matches.add(int(token))
            continue
        token_match = re.fullmatch(r"(\d+)(?:st|nd|rd|th)", token)
        if token_match:
            matches.add(int(token_match.group(1)))
            continue
        alias_index = ordinal_aliases.get(token)
        if alias_index is not None:
            matches.add(alias_index)

    if len(matches) == 1:
        return next(iter(matches))
    return None


def _statement_reference_candidates(reference: str, *, lang: str = "en") -> list[str]:
    normalized = _normalize_statement_action(reference)
    if not normalized:
        return []

    candidates = [normalized]
    trimmed = " ".join(
        token for token in normalized.split() if token not in _statement_reference_noise_tokens(lang=lang)
    ).strip()
    if trimmed and trimmed not in candidates:
        candidates.append(trimmed)
    return candidates


def _statement_shortcut_reference_value(reference: str, *, lang: str = "en") -> str:
    candidates = _statement_reference_candidates(reference, lang=lang)
    if candidates:
        return candidates[-1]
    return _normalize_statement_action(reference)


def _statement_reference_noise_tokens(*, lang: str = "en") -> set[str]:
    del lang
    return {
        *_statement_shortcut_noise_tokens(),
        "detail",
        "details",
        "file",
        "files",
        "import",
        "imports",
        "source",
        "sources",
        "statement",
        "statements",
        "status",
        "выписка",
        "выписки",
        "выписку",
        "детали",
        "деталь",
        "импорт",
        "импорты",
        "исходник",
        "источник",
        "статус",
        "файл",
        "файла",
        "файлы",
        "узинди",
        "узінді",
        "дереккоз",
        "дереккөз",
        "файлын",
        "файлды",
        "джерело",
        "деталі",
        "імпорт",
        "файлу",
        "виписка",
        "виписки",
        "виписку",
    }


def _statement_history_reference_aliases() -> dict[str, int]:
    raw_aliases = {
        1: {
            "1st",
            "first",
            "one",
            "number one",
            "first one",
            "первый",
            "первая",
            "первую",
            "один",
            "одна",
            "одну",
            "бірінші",
            "бір",
            "перший",
            "перша",
            "першу",
        },
        2: {
            "2nd",
            "second",
            "two",
            "number two",
            "second one",
            "второй",
            "вторая",
            "вторую",
            "два",
            "две",
            "екінші",
            "екі",
            "другий",
            "друга",
            "другу",
            "два",
            "дві",
        },
        3: {
            "3rd",
            "third",
            "three",
            "number three",
            "third one",
            "третий",
            "третья",
            "третью",
            "три",
            "үшінші",
            "үш",
            "третій",
            "третя",
            "третю",
        },
        4: {
            "4th",
            "fourth",
            "four",
            "number four",
            "fourth one",
            "четвертый",
            "четвертая",
            "четвертую",
            "четыре",
            "төртінші",
            "төрт",
            "четвертий",
            "четверта",
            "четверту",
            "чотири",
        },
        5: {
            "5th",
            "fifth",
            "five",
            "number five",
            "fifth one",
            "пятый",
            "пятая",
            "пятую",
            "пять",
            "бесінші",
            "бес",
            "пятий",
            "п'ятий",
            "пята",
            "пяту",
            "пять",
        },
    }
    aliases: dict[str, int] = {}
    for index, values in raw_aliases.items():
        for value in values:
            normalized = _normalize_statement_action(value)
            if normalized:
                aliases[normalized] = index
    return aliases


def _is_current_statement_reference(reference: str, *, lang: str = "en") -> bool:
    del lang
    aliases = {
        "current",
        "active",
        "this",
        "current statement",
        "active statement",
        "текущая",
        "текущий",
        "активная",
        "активный",
        "агылдагы",
        "белсенді",
        "поточна",
        "поточний",
        "активна",
        "активний",
    }
    return reference in aliases


def _is_latest_statement_reference(reference: str, *, lang: str = "en") -> bool:
    del lang
    aliases = {
        "latest",
        "last",
        "recent",
        "latest statement",
        "last statement",
        "recent statement",
        "последняя",
        "последний",
        "последняя выписка",
        "соңғы",
        "сонгы",
        "соңғы узінді",
        "сонгы узинди",
        "остання",
        "останній",
        "остання виписка",
    }
    return reference in aliases or _is_current_statement_reference(reference)


def _normalize_statement_action(value: str) -> str:
    return " ".join(
        token
        for token in (_normalize_clarification_token(token) for token in re.findall(r"[\w/-]+", value, flags=re.UNICODE))
        if token
    )


def _looks_like_transaction_log(value: str) -> bool:
    normalized = " ".join(value.strip().split())
    if (
        not normalized
        or StatementParser.looks_like_statement_text(normalized)
        or STATEMENT_ROW_DATE_PATTERN.search(normalized)
    ):
        return False

    parsed = TextTransactionParser.parse(normalized)
    if not parsed or parsed.amount < 100:
        return False

    return len(normalized.split()) <= 8


def _looks_like_clarification_answer(value: str, *, pending: dict | None = None, lang: str = "en") -> bool:
    if match_statement_clarification_choice(value, _current_pending_item(pending), lang=lang):
        return True

    normalized = " ".join(value.strip().split())
    if (
        not normalized
        or len(normalized) > 120
        or StatementParser.looks_like_statement_text(normalized)
        or STATEMENT_ROW_DATE_PATTERN.search(normalized)
        or _looks_like_transaction_log(normalized)
    ):
        return False

    tokens = [_normalize_clarification_token(token) for token in re.findall(r"[\w/-]+", normalized, flags=re.UNICODE)]
    tokens = [token for token in tokens if token]
    if not tokens or len(tokens) > 8:
        return False

    keywords = _clarification_keywords(lang=lang, pending=pending)
    content_tokens = [token for token in tokens if token not in CLARIFICATION_STOP_WORDS]
    if not content_tokens or len(content_tokens) > 6:
        return False

    return any(token in keywords for token in content_tokens) and all(token in keywords for token in content_tokens)


def _clarification_keywords(*, pending: dict | None = None, lang: str = "en") -> set[str]:
    languages = {normalize_language(lang)}
    languages.update(SUPPORTED_LANGUAGES)
    keywords = {
        "business",
        "personal",
        "family",
        "home",
        "private",
        "sales",
        "sale",
        "income",
        "revenue",
        "client",
        "inventory",
        "parts",
        "stock",
        "supplier",
        "payroll",
        "salary",
        "team",
        "rent",
        "utility",
        "utilities",
        "logistics",
        "transport",
        "taxi",
        "fuel",
        "delivery",
        "courier",
        "marketing",
        "ads",
        "advertising",
        "tax",
        "taxes",
        "fee",
        "fees",
        "software",
        "tool",
        "tools",
        "subscription",
        "owner",
        "draw",
        "withdraw",
        "food",
        "living",
        "savings",
        "saving",
        "debt",
        "loan",
        "credit",
        "mortgage",
    }

    for language in languages:
        for account_type in ("business", "personal"):
            keywords.update(_clarification_label_tokens(account_type_label(account_type, language)))
        for _, account_type, life_sector in CLARIFICATION_BUTTON_CHOICES:
            keywords.update(_clarification_label_tokens(account_type_label(account_type, language)))
            keywords.update(_clarification_label_tokens(life_sector_label(life_sector, language)))

    for life_sector in (
        "sales_income",
        "inventory_parts",
        "payroll_team",
        "rent_utilities",
        "logistics_transport",
        "marketing_growth",
        "taxes_fees",
        "tools_software",
        "owner_draw",
        "family_living",
        "savings_debt",
    ):
        keywords.update(_clarification_label_tokens(life_sector.replace("_", " ")))

    pending_item = _current_pending_item(pending)
    if pending_item:
        suggested_account_type = str(pending_item.get("suggested_account_type") or "").strip()
        suggested_life_sector = str(pending_item.get("suggested_life_sector") or "").strip()
        if suggested_account_type:
            keywords.update(_clarification_label_tokens(suggested_account_type))
        if suggested_life_sector:
            keywords.update(_clarification_label_tokens(suggested_life_sector.replace("_", " ")))

    keywords.discard("")
    return keywords


def _clarification_label_tokens(value: str) -> set[str]:
    return {
        normalized
        for raw_token in re.findall(r"[\w/-]+", value, flags=re.UNICODE)
        if (normalized := _normalize_clarification_token(raw_token))
    }


def _normalize_clarification_token(value: str) -> str:
    return value.casefold().strip(" ./_-")


def _latest_statement_text(snapshot: StatementStatusSnapshot, *, lang: str = "en") -> str:
    lines = _statement_snapshot_lines(snapshot, lang=lang)
    lines.append("")
    lines.append(_statement_help_text(lang=lang))
    return "\n".join(lines)


def _statement_history_text(
    history: list[StatementHistorySnapshot],
    *,
    latest_status: StatementStatusSnapshot | None = None,
    lang: str = "en",
) -> str:
    lines = [text("recent_statement_imports_title", lang)]
    if latest_status and latest_status.remaining_clarifications > 0:
        lines.extend(
            [
                text("active_clarification_queue", lang, count=latest_status.remaining_clarifications),
                "",
            ]
        )

    for index, item in enumerate(history, start=1):
        file_label = item.original_filename or item.source_name
        lines.append(f"{index}. {file_label}")
        lines.append(f"   {text('history_item_status', lang, value=statement_status_label(item.parse_status, lang))}")
        lines.append(f"   {text('history_item_imported', lang, value=item.imported_at)}")
        if item.parsed_count is not None:
            lines.append(f"   {text('history_item_parsed', lang, count=item.parsed_count)}")
        if item.auto_count is not None:
            lines.append(f"   {text('history_item_auto', lang, count=item.auto_count)}")
        lines.append(f"   {text('history_item_open_clarifications', lang, count=item.remaining_clarifications)}")
        if index < len(history):
            lines.append("")

    lines.extend(["", text("history_shortcuts", lang), text("history_footer", lang)])
    return "\n".join(lines)


def _statement_detail_text(
    detail: StatementDetailSnapshot,
    *,
    latest_status: StatementStatusSnapshot | None = None,
    pending: dict | None = None,
    lang: str = "en",
) -> str:
    lines = [text("statement_import_detail_title", lang, name=detail.original_filename or detail.source_name)]
    lines.extend(_statement_snapshot_lines(detail, include_source=True, include_imported=True, lang=lang)[1:])
    if detail.is_active and detail.remaining_clarifications > 0:
        lines.append(text("active_clarification_queue", lang, count=detail.remaining_clarifications))
        if pending:
            current_index = int(pending.get("current_index", 0))
            total = len(pending.get("items") or [])
            lines.append(text("resolved_so_far", lang, count=min(current_index, total)))
            lines.append(text("remaining_clarifications", lang, count=max(total - current_index, 0)))

            pending_lines = _statement_detail_pending_lines(_current_pending_item(pending), lang=lang)
            if pending_lines:
                lines.extend(["", *pending_lines])
    elif latest_status and latest_status.remaining_clarifications > 0 and latest_status.imported_statement_id != detail.imported_statement_id:
        lines.append(text("active_clarification_queue", lang, count=latest_status.remaining_clarifications))

    storage_value = _statement_storage_value(detail, lang=lang)
    if storage_value:
        lines.append(text("statement_storage", lang, value=storage_value))
    if detail.note:
        lines.append(text("statement_note", lang, value=detail.note))

    lines.extend(["", *_statement_raw_preview_lines(detail, lang=lang), "", text("statement_detail_footer", lang)])
    return "\n".join(lines)


def _statement_detail_pending_lines(item: dict | None, *, lang: str = "en") -> list[str]:
    if not item:
        return []

    reason = str(item.get("reason") or "").strip()
    parts = [
        StatementImportService._format_pending_item(item, language=lang),
        StatementImportService._format_pending_description(item, language=lang),
        text("statement_reason_label", lang, reason=reason) if reason else "",
        StatementImportService._format_pending_rules(item, language=lang),
        StatementImportService._format_pending_suggestion(item, language=lang),
        StatementImportService._format_primary_choice_hint(item, language=lang),
        StatementImportService._format_same_as_before_hint(item, language=lang),
    ]
    return [part for part in parts if part]


def _pending_status_text(
    *,
    pending_prompt: str,
    latest_status: StatementStatusSnapshot | None,
    pending: dict,
    lang: str = "en",
) -> str:
    current_index = int(pending.get("current_index", 0))
    total = len(pending.get("items") or [])
    resolved_count = min(current_index, total)
    remaining_count = max(total - current_index, 0)

    lines = []
    if latest_status:
        lines.extend(
            [
                text("active_statement", lang, name=latest_status.original_filename or latest_status.source_name),
                text("status", lang, value=statement_status_label(latest_status.parse_status, lang)),
                text("resolved_so_far", lang, count=resolved_count),
                text("remaining_clarifications", lang, count=remaining_count),
                "",
            ]
        )
    lines.append(pending_prompt)
    return "\n".join(lines)


def _no_pending_clarification_text(latest_status: StatementStatusSnapshot | None, *, lang: str = "en") -> str:
    lines = [text("no_pending_statement_clarifications", lang)]
    if latest_status:
        lines.extend(["", *_statement_snapshot_lines(latest_status, include_source=False, include_imported=False, lang=lang)])
    lines.extend(["", _statement_help_text(lang=lang)])
    return "\n".join(lines)


def _completed_statement_text(base_reply: str, latest_status: StatementStatusSnapshot | None, *, lang: str = "en") -> str:
    lines = [base_reply]
    if latest_status:
        lines.extend(["", *_statement_snapshot_lines(latest_status, lang=lang)])
    lines.extend(["", text("completed_statement_footer", lang)])
    return "\n".join(lines)


def _statement_import_blocked_text(
    latest_status: StatementStatusSnapshot | None,
    *,
    pending: dict | None,
    lang: str = "en",
) -> str:
    return text(
        "statement_import_blocked",
        lang,
        name=_statement_name(latest_status),
        count=_remaining_clarifications(pending),
    )


def _statement_snapshot_lines(
    snapshot: StatementStatusSnapshot | StatementDetailSnapshot,
    *,
    include_source: bool = True,
    include_imported: bool = True,
    lang: str = "en",
) -> list[str]:
    lines = [text("latest_statement", lang, name=snapshot.original_filename or snapshot.source_name)]
    if include_source:
        lines.append(text("source", lang, value=snapshot.source_name))
    if include_imported:
        lines.append(text("imported", lang, value=snapshot.imported_at))
    lines.append(text("status", lang, value=statement_status_label(snapshot.parse_status, lang)))
    if snapshot.parsed_count is not None:
        lines.append(text("parsed_items", lang, count=snapshot.parsed_count))
    if snapshot.auto_count is not None:
        lines.append(text("auto_categorized", lang, count=snapshot.auto_count))
    if snapshot.unclear_count is not None:
        lines.append(text("needs_clarification", lang, count=snapshot.unclear_count))
    return lines


def _current_pending_item(pending: dict | None) -> dict | None:
    if not pending:
        return None
    current_index = int(pending.get("current_index", 0))
    items = pending.get("items") or []
    if current_index >= len(items):
        return None
    return items[current_index]


def _remaining_clarifications(pending: dict | None) -> int:
    if not pending:
        return 0
    total = len(pending.get("items") or [])
    current_index = int(pending.get("current_index", 0))
    return max(total - current_index, 0)


def _pending_statement_id(pending: dict | None) -> int | None:
    if not pending:
        return None
    statement_id = pending.get("statement_id")
    if statement_id is None:
        return None
    try:
        return int(statement_id)
    except (TypeError, ValueError):
        return None


def _statement_name(snapshot: StatementStatusSnapshot | None) -> str:
    if not snapshot:
        return "current statement"
    return snapshot.original_filename or snapshot.source_name


def _statement_history_button_label(item: StatementHistorySnapshot, *, index: int) -> str:
    label = item.original_filename or item.source_name or f"statement {index}"
    return _truncate_statement_button_label(f"{index}. {label}")


def _truncate_statement_button_label(value: str, *, limit: int = 32) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip()}..."


def _parse_statement_detail_action(action: str) -> int | None:
    prefix = "detail-"
    if not action.startswith(prefix):
        return None
    statement_id = action[len(prefix) :].strip()
    if not statement_id.isdigit():
        return None
    return int(statement_id)


def _parse_statement_source_action(action: str) -> int | None:
    prefix = "source-"
    if not action.startswith(prefix):
        return None
    statement_id = action[len(prefix) :].strip()
    if not statement_id.isdigit():
        return None
    return int(statement_id)


def _statement_storage_value(detail: StatementDetailSnapshot, *, lang: str = "en") -> str:
    if detail.storage_kind == "virtual_text":
        return text("statement_storage_virtual_text", lang)
    if detail.file_available:
        return text("statement_storage_local_file_available", lang)
    return text("statement_storage_local_file_missing", lang)


def _statement_raw_preview_lines(detail: StatementDetailSnapshot, *, lang: str = "en") -> list[str]:
    if not detail.raw_preview:
        return [text("statement_raw_preview_empty", lang)]

    raw_lines = [line for line in detail.raw_preview.splitlines() if line.strip()]
    lines = [
        text("statement_raw_preview_lines", lang, shown=len(raw_lines), total=detail.raw_line_count),
        *[f"{index}. {line}" for index, line in enumerate(raw_lines, start=1)],
    ]
    if detail.raw_preview_truncated:
        lines.append(text("statement_raw_preview_truncated", lang))
    return lines
