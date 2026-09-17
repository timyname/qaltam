from __future__ import annotations

from pathlib import Path

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.bot.handlers.statements import (
    build_statement_router,
    try_handle_statement_text,
    try_handle_statement_voice,
)
from backend.app.bot.webapp import WebAppTab, build_webapp_url
from backend.app.core.config import get_settings
from backend.app.localization import resolve_user_language, text
from backend.app.services.chat_service import ChatService


def create_bot() -> Bot:
    settings = get_settings()
    return Bot(token=settings.telegram_bot_token)


def create_dispatcher(session_factory: async_sessionmaker) -> Dispatcher:
    router = Router()
    statement_router = build_statement_router(session_factory)

    @router.message(CommandStart())
    async def start_handler(message: Message) -> None:
        if not message.from_user:
            return
        async with session_factory() as session:
            lang = await resolve_user_language(
                session,
                telegram_user_id=message.from_user.id,
                fallback_language_code=getattr(message.from_user, "language_code", None),
            )
            service = ChatService(session)
            reply = await service.start(
                message.from_user.id,
                message.chat.id,
                fallback_language_code=getattr(message.from_user, "language_code", None),
            )
            await session.commit()
        await message.answer(
            reply,
            reply_markup=_webapp_markup(
                text("open_app", lang),
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
            ),
        )

    @router.message(Command("app"))
    async def app_handler(message: Message) -> None:
        if not message.from_user:
            return
        async with session_factory() as session:
            lang = await resolve_user_language(
                session,
                telegram_user_id=message.from_user.id,
                fallback_language_code=getattr(message.from_user, "language_code", None),
            )
        await message.answer(
            text("app_launcher_message", lang),
            reply_markup=_webapp_markup(
                text("open_app", lang),
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
            ),
        )

    @router.message(F.text)
    async def text_handler(message: Message) -> None:
        if not message.from_user or not message.text:
            return
        if await try_handle_statement_text(session_factory, message):
            return
        async with session_factory() as session:
            lang = await resolve_user_language(
                session,
                telegram_user_id=message.from_user.id,
                fallback_language_code=getattr(message.from_user, "language_code", None),
            )
            service = ChatService(session)
            reply = await service.process_text(
                message.from_user.id,
                message.chat.id,
                message.text,
                fallback_language_code=getattr(message.from_user, "language_code", None),
            )
        await message.answer(
            reply,
            reply_markup=_webapp_markup(
                text("review_in_app", lang),
                tab="quick",
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
            ),
        )

    @router.message(F.photo)
    async def photo_handler(message: Message) -> None:
        if not message.from_user or not message.photo:
            return
        settings = get_settings()
        media_dir = Path(settings.local_storage_path) / "imports" / "telegram" / "photos"
        media_dir.mkdir(parents=True, exist_ok=True)
        destination = media_dir / f"{message.photo[-1].file_id}.jpg"
        await message.bot.download(message.photo[-1].file_id, destination=destination)
        async with session_factory() as session:
            lang = await resolve_user_language(
                session,
                telegram_user_id=message.from_user.id,
                fallback_language_code=getattr(message.from_user, "language_code", None),
            )
            service = ChatService(session)
            reply = await service.process_photo(
                message.from_user.id,
                message.chat.id,
                destination,
                fallback_language_code=getattr(message.from_user, "language_code", None),
            )
        await message.answer(
            reply,
            reply_markup=_webapp_markup(
                text("review_receipt_lane", lang),
                tab="cashier",
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
            ),
        )

    @router.message(F.voice)
    async def voice_handler(message: Message) -> None:
        if not message.from_user or not message.voice:
            return
        settings = get_settings()
        media_dir = Path(settings.local_storage_path) / "imports" / "telegram" / "voice"
        media_dir.mkdir(parents=True, exist_ok=True)
        destination = media_dir / f"{message.voice.file_id}.ogg"
        await message.bot.download(message.voice.file_id, destination=destination)
        if await try_handle_statement_voice(session_factory, message, destination):
            return
        async with session_factory() as session:
            lang = await resolve_user_language(
                session,
                telegram_user_id=message.from_user.id,
                fallback_language_code=getattr(message.from_user, "language_code", None),
            )
            service = ChatService(session)
            reply = await service.process_voice(
                message.from_user.id,
                message.chat.id,
                destination,
                fallback_language_code=getattr(message.from_user, "language_code", None),
            )
        await message.answer(
            reply,
            reply_markup=_webapp_markup(
                text("review_in_app", lang),
                tab="quick",
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
            ),
        )

    dp = Dispatcher()
    dp.include_router(statement_router)
    dp.include_router(router)
    return dp


def _webapp_markup(
    button_text: str = "Open QALTAM / FOCUS",
    *,
    tab: WebAppTab | None = None,
    telegram_user_id: int | None = None,
    telegram_chat_id: int | None = None,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=button_text,
                    web_app=WebAppInfo(
                        url=build_webapp_url(
                            tab=tab,
                            telegram_user_id=telegram_user_id,
                            telegram_chat_id=telegram_chat_id,
                        )
                    ),
                )
            ]
        ]
    )
