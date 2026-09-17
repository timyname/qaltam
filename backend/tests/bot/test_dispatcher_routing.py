from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage, TelegramMethod
from aiogram.types import Message as TelegramMessage
from aiogram.types import Update

import backend.app.bot.factory as bot_factory
import backend.app.bot.handlers.statements as statement_handlers
from backend.app.bot.factory import create_dispatcher
from backend.app.bot.webapp import build_webapp_url
from backend.app.core.config import get_settings
from backend.app.services.statement_import_service import StatementStatusSnapshot


class DummySession:
    def __init__(self) -> None:
        self.commit_calls = 0

    async def commit(self) -> None:
        self.commit_calls += 1

    async def execute(self, statement):
        del statement
        return DummyScalarResult()


class DummyScalarResult:
    def scalar_one_or_none(self):
        return None


class DummySessionFactory:
    def __init__(self) -> None:
        self.session = DummySession()

    def __call__(self) -> DummySessionFactory:
        return self

    async def __aenter__(self) -> DummySession:
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeTelegramSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod] = []
        self._message_id = 1000

    async def close(self) -> None:
        return None

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod,
        timeout: int | None = None,
    ):
        del timeout
        self.calls.append(method)
        if isinstance(method, SendMessage):
            self._message_id += 1
            return TelegramMessage.model_validate(
                {
                    "message_id": self._message_id,
                    "date": int(datetime(2026, 8, 13, 9, 0, 0).timestamp()),
                    "chat": {"id": int(method.chat_id), "type": "private"},
                    "text": method.text,
                },
                context={"bot": bot},
            )
        if isinstance(method, EditMessageText):
            return TelegramMessage.model_validate(
                {
                    "message_id": int(method.message_id),
                    "date": int(datetime(2026, 8, 13, 9, 0, 0).timestamp()),
                    "chat": {"id": int(method.chat_id), "type": "private"},
                    "text": method.text,
                },
                context={"bot": bot},
            )
        if isinstance(method, AnswerCallbackQuery):
            return True
        raise AssertionError(f"Unexpected Telegram method: {type(method).__name__}")

    async def stream_content(
        self,
        url: str,
        headers: dict[str, object] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        del url, headers, timeout, chunk_size, raise_for_status
        if False:
            yield b""


def _build_update(*, text: str, user_id: int = 42, chat_id: int = 99, message_id: int = 1) -> Update:
    return Update.model_validate(
        {
            "update_id": 9000 + message_id,
            "message": {
                "message_id": message_id,
                "date": int(datetime(2026, 8, 13, 8, 30, 0).timestamp()),
                "chat": {"id": chat_id, "type": "private"},
                "from": {
                    "id": user_id,
                    "is_bot": False,
                    "first_name": "Qaltam",
                },
                "text": text,
            },
        }
    )


def _build_photo_update(*, file_id: str = "photo-file-1", user_id: int = 42, chat_id: int = 99, message_id: int = 1) -> Update:
    return Update.model_validate(
        {
            "update_id": 9100 + message_id,
            "message": {
                "message_id": message_id,
                "date": int(datetime(2026, 8, 13, 8, 35, 0).timestamp()),
                "chat": {"id": chat_id, "type": "private"},
                "from": {
                    "id": user_id,
                    "is_bot": False,
                    "first_name": "Qaltam",
                },
                "photo": [
                    {
                        "file_id": file_id,
                        "file_unique_id": f"{file_id}-unique",
                        "width": 320,
                        "height": 240,
                    }
                ],
            },
        }
    )


def _build_voice_update(*, file_id: str = "voice-file-1", user_id: int = 42, chat_id: int = 99, message_id: int = 1) -> Update:
    return Update.model_validate(
        {
            "update_id": 9200 + message_id,
            "message": {
                "message_id": message_id,
                "date": int(datetime(2026, 8, 13, 8, 40, 0).timestamp()),
                "chat": {"id": chat_id, "type": "private"},
                "from": {
                    "id": user_id,
                    "is_bot": False,
                    "first_name": "Qaltam",
                },
                "voice": {
                    "file_id": file_id,
                    "file_unique_id": f"{file_id}-unique",
                    "duration": 7,
                    "mime_type": "audio/ogg",
                    "file_size": 128,
                },
            },
        }
    )


def _build_callback_update(
    *,
    data: str,
    user_id: int = 42,
    chat_id: int = 99,
    message_id: int = 1,
    callback_id: str = "callback-1",
) -> Update:
    return Update.model_validate(
        {
            "update_id": 9300 + message_id,
            "callback_query": {
                "id": callback_id,
                "from": {
                    "id": user_id,
                    "is_bot": False,
                    "first_name": "Qaltam",
                },
                "chat_instance": "statement-chat-instance",
                "data": data,
                "message": {
                    "message_id": message_id,
                    "date": int(datetime(2026, 8, 13, 8, 45, 0).timestamp()),
                    "chat": {"id": chat_id, "type": "private"},
                    "text": "Choose statement action",
                },
            },
        }
    )


def _sent_texts(session: FakeTelegramSession) -> list[str]:
    return [method.text for method in session.calls if isinstance(method, SendMessage)]


def _sent_messages(session: FakeTelegramSession) -> list[SendMessage]:
    return [method for method in session.calls if isinstance(method, SendMessage)]


def _edited_texts(session: FakeTelegramSession) -> list[str]:
    return [method.text for method in session.calls if isinstance(method, EditMessageText)]


def _edited_messages(session: FakeTelegramSession) -> list[EditMessageText]:
    return [method for method in session.calls if isinstance(method, EditMessageText)]


def _callback_answers(session: FakeTelegramSession) -> list[AnswerCallbackQuery]:
    return [method for method in session.calls if isinstance(method, AnswerCallbackQuery)]


@pytest.mark.asyncio
async def test_dispatcher_routes_statement_text_before_generic_chat(monkeypatch) -> None:
    statement_calls: list[tuple[int, int, str]] = []
    chat_calls: list[tuple[int, int, str]] = []

    async def fake_try_handle_statement_text(session_factory, message) -> bool:
        del session_factory
        statement_calls.append((message.from_user.id, message.chat.id, message.text))
        await message.answer("statement route reply")
        return True

    class FakeChatService:
        def __init__(self, session) -> None:
            del session

        async def process_text(
            self,
            telegram_user_id: int,
            telegram_chat_id: int,
            text: str,
            *,
            fallback_language_code: str | None = None,
        ) -> str:
            del fallback_language_code
            chat_calls.append((telegram_user_id, telegram_chat_id, text))
            return "chat fallback reply"

    monkeypatch.setattr(bot_factory, "try_handle_statement_text", fake_try_handle_statement_text)
    monkeypatch.setattr(bot_factory, "ChatService", FakeChatService)

    session_factory = DummySessionFactory()
    dispatcher = create_dispatcher(session_factory)
    telegram_session = FakeTelegramSession()
    bot = Bot(token="123456:TESTTOKEN", session=telegram_session)

    await dispatcher.feed_update(bot, _build_update(text="2026-08-13 Client LLP +150000"))

    assert statement_calls == [(42, 99, "2026-08-13 Client LLP +150000")]
    assert chat_calls == []
    assert _sent_texts(telegram_session) == ["statement route reply"]


@pytest.mark.asyncio
async def test_dispatcher_falls_back_to_generic_chat_when_statement_handler_declines(monkeypatch) -> None:
    statement_calls: list[str] = []
    chat_calls: list[tuple[int, int, str]] = []

    async def fake_try_handle_statement_text(session_factory, message) -> bool:
        del session_factory
        statement_calls.append(message.text)
        return False

    class FakeChatService:
        def __init__(self, session) -> None:
            del session

        async def process_text(
            self,
            telegram_user_id: int,
            telegram_chat_id: int,
            text: str,
            *,
            fallback_language_code: str | None = None,
        ) -> str:
            del fallback_language_code
            chat_calls.append((telegram_user_id, telegram_chat_id, text))
            return "chat fallback reply"

    monkeypatch.setattr(bot_factory, "try_handle_statement_text", fake_try_handle_statement_text)
    monkeypatch.setattr(bot_factory, "ChatService", FakeChatService)

    session_factory = DummySessionFactory()
    dispatcher = create_dispatcher(session_factory)
    telegram_session = FakeTelegramSession()
    bot = Bot(token="123456:TESTTOKEN", session=telegram_session)

    await dispatcher.feed_update(bot, _build_update(text="Need help with margins"))

    assert statement_calls == ["Need help with margins"]
    assert chat_calls == [(42, 99, "Need help with margins")]
    assert _sent_texts(telegram_session) == ["chat fallback reply"]
    send_messages = _sent_messages(telegram_session)
    assert len(send_messages) == 1
    assert send_messages[0].reply_markup is not None
    button = send_messages[0].reply_markup.inline_keyboard[0][0]
    assert button.text == "Review in QALTAM / FOCUS"
    assert button.web_app.url == build_webapp_url(tab="quick", telegram_user_id=42, telegram_chat_id=99)


@pytest.mark.asyncio
async def test_dispatcher_falls_back_to_generic_chat_when_pending_clarification_receives_non_answer_text(monkeypatch) -> None:
    chat_calls: list[tuple[int, int, str]] = []

    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def get_pending_clarification(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return {
                "current_index": 0,
                "items": [
                    {
                        "suggested_account_type": "business",
                        "suggested_life_sector": "inventory_parts",
                    }
                ],
            }

        async def process_clarification_text(self, **kwargs):
            raise AssertionError("process_clarification_text should not run for non-answer text")

        async def import_text(self, **kwargs):
            raise AssertionError("import_text should not run for non-answer text")

    class FakeChatService:
        def __init__(self, session) -> None:
            del session

        async def process_text(
            self,
            telegram_user_id: int,
            telegram_chat_id: int,
            text: str,
            *,
            fallback_language_code: str | None = None,
        ) -> str:
            del fallback_language_code
            chat_calls.append((telegram_user_id, telegram_chat_id, text))
            return "chat fallback reply"

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)
    monkeypatch.setattr(bot_factory, "ChatService", FakeChatService)

    session_factory = DummySessionFactory()
    dispatcher = create_dispatcher(session_factory)
    telegram_session = FakeTelegramSession()
    bot = Bot(token="123456:TESTTOKEN", session=telegram_session)

    await dispatcher.feed_update(bot, _build_update(text="Need help with margins"))

    assert chat_calls == [(42, 99, "Need help with margins")]
    assert _sent_texts(telegram_session) == ["chat fallback reply"]
    send_messages = _sent_messages(telegram_session)
    assert len(send_messages) == 1
    assert send_messages[0].reply_markup is not None
    button = send_messages[0].reply_markup.inline_keyboard[0][0]
    assert button.text == "Review in QALTAM / FOCUS"
    assert button.web_app.url == build_webapp_url(tab="quick", telegram_user_id=42, telegram_chat_id=99)


@pytest.mark.asyncio
async def test_dispatcher_app_command_sends_webapp_launcher() -> None:
    session_factory = DummySessionFactory()
    dispatcher = create_dispatcher(session_factory)
    telegram_session = FakeTelegramSession()
    bot = Bot(token="123456:TESTTOKEN", session=telegram_session)

    await dispatcher.feed_update(bot, _build_update(text="/app"))

    send_messages = [method for method in telegram_session.calls if isinstance(method, SendMessage)]

    assert len(send_messages) == 1
    assert "Mini App" in send_messages[0].text
    assert send_messages[0].reply_markup is not None
    button = send_messages[0].reply_markup.inline_keyboard[0][0]
    assert button.text == "Open QALTAM / FOCUS"
    assert button.web_app.url == build_webapp_url(telegram_user_id=42, telegram_chat_id=99)


@pytest.mark.asyncio
async def test_dispatcher_routes_voice_to_statement_handler_before_generic_chat(monkeypatch, tmp_path) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "local_storage_path", str(tmp_path), raising=False)

    download_calls: list[tuple[str, Path]] = []
    statement_calls: list[tuple[int, int, str, str]] = []
    chat_calls: list[tuple[int, int, str]] = []

    async def fake_download(file_id: str, destination: Path) -> None:
        download_calls.append((file_id, destination))
        destination.write_text("voice", encoding="utf-8")

    async def fake_try_handle_statement_voice(session_factory, message, destination: Path) -> bool:
        del session_factory
        statement_calls.append((message.from_user.id, message.chat.id, message.voice.file_id, destination.suffix))
        await message.answer("statement voice reply")
        return True

    class FakeChatService:
        def __init__(self, session) -> None:
            del session

        async def process_voice(
            self,
            telegram_user_id: int,
            telegram_chat_id: int,
            audio_path: Path,
            *,
            fallback_language_code: str | None = None,
        ) -> str:
            del fallback_language_code
            chat_calls.append((telegram_user_id, telegram_chat_id, str(audio_path)))
            return "chat voice fallback"

    monkeypatch.setattr(bot_factory, "try_handle_statement_voice", fake_try_handle_statement_voice)
    monkeypatch.setattr(bot_factory, "ChatService", FakeChatService)

    session_factory = DummySessionFactory()
    dispatcher = create_dispatcher(session_factory)
    telegram_session = FakeTelegramSession()
    bot = Bot(token="123456:TESTTOKEN", session=telegram_session)
    monkeypatch.setattr(bot, "download", fake_download)

    await dispatcher.feed_update(bot, _build_voice_update())

    assert len(download_calls) == 1
    assert download_calls[0][0] == "voice-file-1"
    assert download_calls[0][1].exists()
    assert statement_calls == [(42, 99, "voice-file-1", ".ogg")]
    assert chat_calls == []
    assert _sent_texts(telegram_session) == ["statement voice reply"]


@pytest.mark.asyncio
async def test_dispatcher_falls_back_to_generic_voice_chat_when_statement_handler_declines(monkeypatch, tmp_path) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "local_storage_path", str(tmp_path), raising=False)

    download_calls: list[tuple[str, Path]] = []
    statement_calls: list[str] = []
    chat_calls: list[tuple[int, int, str]] = []

    async def fake_download(file_id: str, destination: Path) -> None:
        download_calls.append((file_id, destination))
        destination.write_text("voice", encoding="utf-8")

    async def fake_try_handle_statement_voice(session_factory, message, destination: Path) -> bool:
        del session_factory
        statement_calls.append(f"{message.voice.file_id}:{destination.suffix}")
        return False

    class FakeChatService:
        def __init__(self, session) -> None:
            del session

        async def process_voice(
            self,
            telegram_user_id: int,
            telegram_chat_id: int,
            audio_path: Path,
            *,
            fallback_language_code: str | None = None,
        ) -> str:
            del fallback_language_code
            chat_calls.append((telegram_user_id, telegram_chat_id, str(audio_path)))
            return "chat voice fallback"

    monkeypatch.setattr(bot_factory, "try_handle_statement_voice", fake_try_handle_statement_voice)
    monkeypatch.setattr(bot_factory, "ChatService", FakeChatService)

    session_factory = DummySessionFactory()
    dispatcher = create_dispatcher(session_factory)
    telegram_session = FakeTelegramSession()
    bot = Bot(token="123456:TESTTOKEN", session=telegram_session)
    monkeypatch.setattr(bot, "download", fake_download)

    await dispatcher.feed_update(bot, _build_voice_update(file_id="voice-file-2"))

    assert len(download_calls) == 1
    assert statement_calls == ["voice-file-2:.ogg"]
    assert len(chat_calls) == 1
    assert chat_calls[0][0:2] == (42, 99)
    assert chat_calls[0][2].endswith("voice-file-2.ogg")
    assert _sent_texts(telegram_session) == ["chat voice fallback"]
    send_messages = _sent_messages(telegram_session)
    assert len(send_messages) == 1
    assert send_messages[0].reply_markup is not None
    button = send_messages[0].reply_markup.inline_keyboard[0][0]
    assert button.text == "Review in QALTAM / FOCUS"
    assert button.web_app.url == build_webapp_url(tab="quick", telegram_user_id=42, telegram_chat_id=99)


@pytest.mark.asyncio
async def test_dispatcher_routes_photo_to_generic_chat_service(monkeypatch, tmp_path) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "local_storage_path", str(tmp_path), raising=False)

    download_calls: list[tuple[str, Path]] = []
    photo_calls: list[tuple[int, int, str]] = []

    async def fake_download(file_id: str, destination: Path) -> None:
        download_calls.append((file_id, destination))
        destination.write_text("photo", encoding="utf-8")

    class FakeChatService:
        def __init__(self, session) -> None:
            del session

        async def process_photo(
            self,
            telegram_user_id: int,
            telegram_chat_id: int,
            image_path: Path,
            *,
            fallback_language_code: str | None = None,
        ) -> str:
            del fallback_language_code
            photo_calls.append((telegram_user_id, telegram_chat_id, str(image_path)))
            return "chat photo reply"

    monkeypatch.setattr(bot_factory, "ChatService", FakeChatService)

    session_factory = DummySessionFactory()
    dispatcher = create_dispatcher(session_factory)
    telegram_session = FakeTelegramSession()
    bot = Bot(token="123456:TESTTOKEN", session=telegram_session)
    monkeypatch.setattr(bot, "download", fake_download)

    await dispatcher.feed_update(bot, _build_photo_update(file_id="photo-file-7"))

    assert len(download_calls) == 1
    assert download_calls[0][0] == "photo-file-7"
    assert download_calls[0][1].exists()
    assert len(photo_calls) == 1
    assert photo_calls[0][0:2] == (42, 99)
    assert photo_calls[0][2].endswith("photo-file-7.jpg")
    assert _sent_texts(telegram_session) == ["chat photo reply"]
    send_messages = _sent_messages(telegram_session)
    assert len(send_messages) == 1
    assert send_messages[0].reply_markup is not None
    button = send_messages[0].reply_markup.inline_keyboard[0][0]
    assert button.text == "Review receipt lane"
    assert button.web_app.url == build_webapp_url(tab="cashier", telegram_user_id=42, telegram_chat_id=99)


@pytest.mark.asyncio
async def test_dispatcher_routes_statement_status_callback(monkeypatch) -> None:
    callback_calls: list[tuple[int, str]] = []

    async def fake_build_statement_callback_reply(
        service,
        *,
        telegram_user_id: int,
        telegram_chat_id: int | None = None,
        action: str,
        lang: str = "en",
    ):
        del service
        assert telegram_chat_id == 99
        del lang
        callback_calls.append((telegram_user_id, action))
        return ("Latest statement from callback", None, "Loaded latest statement status", False)

    monkeypatch.setattr(statement_handlers, "build_statement_callback_reply", fake_build_statement_callback_reply)

    session_factory = DummySessionFactory()
    dispatcher = create_dispatcher(session_factory)
    telegram_session = FakeTelegramSession()
    bot = Bot(token="123456:TESTTOKEN", session=telegram_session)

    await dispatcher.feed_update(bot, _build_callback_update(data="stmt:status:latest"))

    assert callback_calls == [(42, "latest")]
    callback_answers = _callback_answers(telegram_session)
    assert len(callback_answers) == 1
    assert callback_answers[0].text == "Loaded latest statement status"
    assert callback_answers[0].show_alert is False
    assert _sent_texts(telegram_session) == []
    assert _edited_texts(telegram_session) == ["Latest statement from callback"]
    edited_messages = _edited_messages(telegram_session)
    assert len(edited_messages) == 1
    assert edited_messages[0].message_id == 1
    assert edited_messages[0].chat_id == 99


@pytest.mark.asyncio
async def test_dispatcher_routes_statement_clarification_choice_callback(monkeypatch) -> None:
    choice_calls: list[tuple[int, int, str, str]] = []

    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def process_clarification_choice(
            self,
            *,
            telegram_user_id: int,
            telegram_chat_id: int,
            account_type: str,
            life_sector: str,
            language: str = "en",
        ) -> str:
            assert language == "en"
            choice_calls.append((telegram_user_id, telegram_chat_id, account_type, life_sector))
            return "Statement import complete. All unclear items were resolved and saved into memory."

        async def get_pending_clarification(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return None

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=21,
                source_name="Kaspi",
                original_filename="callback.csv",
                parse_status="completed",
                imported_at="2026-08-13 13:20",
                parsed_count=4,
                auto_count=4,
                unclear_count=0,
                remaining_clarifications=0,
            )

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)

    session_factory = DummySessionFactory()
    dispatcher = create_dispatcher(session_factory)
    telegram_session = FakeTelegramSession()
    bot = Bot(token="123456:TESTTOKEN", session=telegram_session)

    await dispatcher.feed_update(bot, _build_callback_update(data="stmt:business:sales_income", callback_id="callback-2"))

    assert choice_calls == [(42, 99, "business", "sales_income")]
    assert session_factory.session.commit_calls == 1
    callback_answers = _callback_answers(telegram_session)
    assert len(callback_answers) == 1
    assert callback_answers[0].text == "Saved"
    assert _sent_texts(telegram_session) == []
    edited_text = _edited_texts(telegram_session)
    assert len(edited_text) == 1
    assert "Statement import complete." in edited_text[0]
    assert "Latest statement: callback.csv" in edited_text[0]


@pytest.mark.asyncio
async def test_dispatcher_refreshes_stale_statement_clarification_callback(monkeypatch) -> None:
    choice_calls: list[tuple[int, int, str, str]] = []
    refresh_calls: list[tuple[int, int | None, str, str]] = []

    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def process_clarification_choice(
            self,
            *,
            telegram_user_id: int,
            telegram_chat_id: int,
            account_type: str,
            life_sector: str,
            language: str = "en",
        ) -> None:
            assert language == "en"
            choice_calls.append((telegram_user_id, telegram_chat_id, account_type, life_sector))
            return None

        async def get_pending_clarification(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return None

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=22,
                source_name="Kaspi",
                original_filename="resolved.csv",
                parse_status="completed",
                imported_at="2026-08-13 13:35",
                parsed_count=4,
                auto_count=4,
                unclear_count=0,
                remaining_clarifications=0,
            )

    async def fake_build_statement_callback_reply(
        service,
        *,
        telegram_user_id: int,
        telegram_chat_id: int | None = None,
        action: str,
        lang: str = "en",
    ):
        assert isinstance(service, FakeStatementImportService)
        refresh_calls.append((telegram_user_id, telegram_chat_id, action, lang))
        return (
            "No pending statement clarifications right now.\n\nLatest statement: resolved.csv",
            None,
            "No pending statement clarification.",
            True,
        )

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)
    monkeypatch.setattr(statement_handlers, "build_statement_callback_reply", fake_build_statement_callback_reply)

    session_factory = DummySessionFactory()
    dispatcher = create_dispatcher(session_factory)
    telegram_session = FakeTelegramSession()
    bot = Bot(token="123456:TESTTOKEN", session=telegram_session)

    await dispatcher.feed_update(bot, _build_callback_update(data="stmt:business:sales_income", callback_id="callback-3"))

    assert choice_calls == [(42, 99, "business", "sales_income")]
    assert refresh_calls == [(42, 99, "resume", "en")]
    callback_answers = _callback_answers(telegram_session)
    assert len(callback_answers) == 1
    assert callback_answers[0].text == "No pending statement clarification."
    assert callback_answers[0].show_alert is True
    assert _sent_texts(telegram_session) == []
    assert _edited_texts(telegram_session) == [
        "No pending statement clarifications right now.\n\nLatest statement: resolved.csv"
    ]
