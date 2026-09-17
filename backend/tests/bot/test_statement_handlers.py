from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.app.bot.handlers.statements as statement_handlers
from backend.app.bot.webapp import build_webapp_url
from backend.app.bot.handlers.statements import (
    _clarification_markup,
    _no_pending_clarification_text,
    _send_statement_source_message,
    _statement_history_text,
    _statement_help_markup,
    _statement_help_text,
    _statement_status_markup,
    build_statement_callback_reply,
    build_statement_status_reply,
    handle_statement_document,
    try_handle_statement_text,
    try_handle_statement_voice,
)
from backend.app.services.statement_import_service import (
    ActiveStatementImportConflictError,
    StatementDetailSnapshot,
    StatementHistorySnapshot,
    StatementStatusSnapshot,
    StatementSourceSnapshot,
)
from backend.app.core.config import get_settings


def _flatten_markup(markup) -> list:
    return [button for row in markup.inline_keyboard for button in row]


def test_clarification_markup_prioritizes_suggested_choice_when_no_learned_rule_exists() -> None:
    markup = _clarification_markup(
        {
            "suggested_account_type": "business",
            "suggested_life_sector": "inventory_parts",
        }
    )

    first_button = markup.inline_keyboard[0][0]
    assert first_button.text == "Suggested: Business / Inventory / Parts"
    assert first_button.callback_data == "stmt:business:inventory_parts"

    buttons = _flatten_markup(markup)
    refresh_button = next(button for button in buttons if button.callback_data == "stmt:status:resume")
    latest_button = next(button for button in buttons if button.callback_data == "stmt:status:latest")
    history_button = next(button for button in buttons if button.callback_data == "stmt:status:history")
    webapp_button = next(button for button in buttons if button.text == "Open QALTAM / FOCUS")

    assert refresh_button.text == "Refresh active statement"
    assert refresh_button.callback_data == "stmt:status:resume"
    assert latest_button.text == "Latest statement status"
    assert latest_button.callback_data == "stmt:status:latest"
    assert history_button.text == "Recent statement imports"
    assert history_button.callback_data == "stmt:status:history"
    assert webapp_button.text == "Open QALTAM / FOCUS"
    assert webapp_button.web_app.url == build_webapp_url(tab="quick", focus="clarify")


def test_clarification_markup_prioritizes_learned_rule_before_suggestion() -> None:
    markup = _clarification_markup(
        {
            "suggested_account_type": "business",
            "suggested_life_sector": "sales_income",
            "matched_rules": [
                {
                    "account_type": "business",
                    "life_sector": "inventory_parts",
                    "explanation": "Arman T. is usually a supplier payment.",
                }
            ],
        }
    )

    first_button = markup.inline_keyboard[0][0]
    second_button = markup.inline_keyboard[1][0]

    assert first_button.text == "Learned: Business / Inventory / Parts"
    assert first_button.callback_data == "stmt:business:inventory_parts"
    assert second_button.text == "Suggested: Business / Sales / Income"
    assert second_button.callback_data == "stmt:business:sales_income"


def test_clarification_markup_surfaces_learned_rule_without_duplicate_generic_choice() -> None:
    markup = _clarification_markup(
        {
            "matched_rules": [
                {
                    "account_type": "personal",
                    "life_sector": "family_living",
                    "explanation": "Usually a family support transfer.",
                }
            ]
        }
    )

    buttons = _flatten_markup(markup)
    learned_buttons = [button for button in buttons if button.callback_data == "stmt:personal:family_living"]

    assert learned_buttons
    assert learned_buttons[0].text == "Learned: Personal / Family / Living"
    assert len(learned_buttons) == 1


def test_clarification_markup_can_render_russian_labels() -> None:
    markup = _clarification_markup(
        {
            "suggested_account_type": "business",
            "suggested_life_sector": "inventory_parts",
        },
        lang="ru",
    )

    first_button = markup.inline_keyboard[0][0]
    assert first_button.text == "Подсказка: Бизнес / Товар / Запчасти"
    webapp_button = next(button for button in _flatten_markup(markup) if button.web_app is not None)
    assert webapp_button.text == "Открыть QALTAM / FOCUS"


def test_clarification_markup_passes_statement_id_to_webapp_url() -> None:
    markup = _clarification_markup(
        {
            "suggested_account_type": "business",
            "suggested_life_sector": "inventory_parts",
        },
        statement_id=14,
    )

    webapp_button = next(button for button in _flatten_markup(markup) if button.web_app is not None)
    assert webapp_button.web_app.url == build_webapp_url(tab="quick", focus="clarify", statement_id=14)


def test_statement_help_markup_opens_webapp() -> None:
    markup = _statement_help_markup()

    latest_button = markup.inline_keyboard[0][0]
    history_button = markup.inline_keyboard[1][0]
    webapp_button = markup.inline_keyboard[2][0]
    assert latest_button.text == "Latest statement status"
    assert latest_button.callback_data == "stmt:status:latest"
    assert history_button.text == "Recent statement imports"
    assert history_button.callback_data == "stmt:status:history"
    assert webapp_button.text == "Open QALTAM / FOCUS"
    assert webapp_button.web_app.url == build_webapp_url(tab="quick", focus="statement")


def test_statement_status_markup_can_include_resume_button() -> None:
    markup = _statement_status_markup(has_pending=True, source_statement_id=11)

    assert markup.inline_keyboard[0][0].text == "Resume clarification"
    assert markup.inline_keyboard[0][0].callback_data == "stmt:status:resume"
    assert markup.inline_keyboard[1][0].text == "Latest statement status"
    assert markup.inline_keyboard[2][0].text == "Send source file"
    assert markup.inline_keyboard[2][0].callback_data == "stmt:status:source-11"
    assert markup.inline_keyboard[3][0].text == "Recent statement imports"
    assert markup.inline_keyboard[4][0].web_app.url == build_webapp_url(tab="quick", focus="clarify")


def test_statement_status_markup_uses_statement_focus_without_pending_queue() -> None:
    markup = _statement_status_markup()

    assert markup.inline_keyboard[0][0].text == "Latest statement status"
    assert markup.inline_keyboard[1][0].text == "Recent statement imports"
    assert markup.inline_keyboard[2][0].web_app.url == build_webapp_url(tab="quick", focus="statement")


def test_statement_status_markup_passes_statement_id_to_webapp_url() -> None:
    markup = _statement_status_markup(statement_id=19)

    assert markup.inline_keyboard[2][0].web_app.url == build_webapp_url(tab="quick", focus="statement", statement_id=19)


def test_statement_status_markup_can_include_latest_source_button_without_changing_webapp_target() -> None:
    markup = _statement_status_markup(statement_id=19, source_statement_id=8)

    assert markup.inline_keyboard[0][0].text == "Latest statement status"
    assert markup.inline_keyboard[1][0].text == "Send source file"
    assert markup.inline_keyboard[1][0].callback_data == "stmt:status:source-8"
    assert markup.inline_keyboard[3][0].web_app.url == build_webapp_url(tab="quick", focus="statement", statement_id=19)


def test_statement_help_text_mentions_supported_flows() -> None:
    help_text = _statement_help_text()

    assert "PDF, CSV, XLSX, or XLS" in help_text
    assert "/clarify" in help_text
    assert "Mini App" in help_text


def test_statement_help_text_can_render_russian_copy() -> None:
    help_text = _statement_help_text(lang="ru")

    assert "банковскую выписку" in help_text
    assert "/clarify" in help_text
    assert "Mini App" in help_text


def test_no_pending_clarification_text_includes_latest_status() -> None:
    text = _no_pending_clarification_text(
        StatementStatusSnapshot(
            imported_statement_id=7,
            source_name="Kaspi",
            original_filename="august.csv",
            parse_status="completed",
            imported_at="2026-08-13 09:10",
            parsed_count=14,
            auto_count=12,
            unclear_count=0,
            remaining_clarifications=0,
        )
    )

    assert "No pending statement clarifications right now." in text
    assert "Latest statement: august.csv" in text
    assert "Status: Completed" in text
    assert "Parsed items: 14" in text
    assert "Auto-categorized: 12" in text


def test_statement_history_text_renders_recent_imports_and_active_queue() -> None:
    text = _statement_history_text(
        [
            StatementHistorySnapshot(
                imported_statement_id=11,
                source_name="Kaspi",
                original_filename="kaspi_aug.csv",
                parse_status="clarification_required",
                imported_at="2026-08-13 14:10",
                parsed_count=6,
                auto_count=4,
                unclear_count=2,
                remaining_clarifications=2,
            ),
            StatementHistorySnapshot(
                imported_statement_id=10,
                source_name="Halyk",
                original_filename="halyk_aug.xlsx",
                parse_status="completed",
                imported_at="2026-08-12 18:45",
                parsed_count=9,
                auto_count=9,
                unclear_count=0,
                remaining_clarifications=0,
            ),
        ],
        latest_status=StatementStatusSnapshot(
            imported_statement_id=11,
            source_name="Kaspi",
            original_filename="kaspi_aug.csv",
            parse_status="clarification_required",
            imported_at="2026-08-13 14:10",
            parsed_count=6,
            auto_count=4,
            unclear_count=2,
            remaining_clarifications=2,
        ),
    )

    assert "Recent statement imports:" in text
    assert "Active clarification queue: 2 still open" in text
    assert "1. kaspi_aug.csv" in text
    assert "Open clarifications: 2" in text
    assert "2. halyk_aug.xlsx" in text
    assert "You can also use the buttons below." in text
    assert "Use /clarify to jump back into the active queue" in text


def test_parse_statement_shortcut_request_prefers_longest_source_prefix() -> None:
    assert statement_handlers._parse_statement_shortcut_request("send source file", lang="en") == (
        "source",
        "current",
    )


def test_parse_statement_shortcut_request_accepts_reference_first_phrasing() -> None:
    assert statement_handlers._parse_statement_shortcut_request("latest source file", lang="en") == (
        "source",
        "latest",
    )
    assert statement_handlers._parse_statement_shortcut_request("please latest statement detail", lang="en") == (
        "detail",
        "latest",
    )


def test_statement_history_index_from_reference_accepts_spoken_ordinals_across_languages() -> None:
    assert statement_handlers._statement_history_index_from_reference("second") == 2
    assert statement_handlers._statement_history_index_from_reference("show the third import") == 3
    assert statement_handlers._statement_history_index_from_reference("вторую выписку") == 2
    assert statement_handlers._statement_history_index_from_reference("екінші импорт") == 2
    assert statement_handlers._statement_history_index_from_reference("4th statement") == 4
    assert statement_handlers._statement_history_index_from_reference("latest statement") is None


def test_statement_reference_candidates_strip_statement_context_words() -> None:
    assert statement_handlers._statement_reference_candidates("latest statement detail", lang="en") == [
        "latest statement detail",
        "latest",
    ]


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
    def __init__(self, session: DummySession | None = None) -> None:
        self.session = session or DummySession()

    def __call__(self) -> "DummySessionFactory":
        return self

    async def __aenter__(self) -> DummySession:
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeBot:
    def __init__(self) -> None:
        self.downloads: list[tuple[str, Path]] = []

    async def download(self, file_id: str, destination: Path) -> None:
        self.downloads.append((file_id, destination))
        destination.write_text("stub", encoding="utf-8")


class FakeMessage:
    def __init__(
        self,
        *,
        text: str | None = None,
        file_name: str | None = None,
        file_id: str = "file-1",
        user_id: int = 42,
        chat_id: int = 99,
    ) -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.chat = SimpleNamespace(id=chat_id)
        self.bot = FakeBot()
        self.answers: list[dict[str, object | None]] = []
        self.documents: list[dict[str, object | None]] = []
        self.document = (
            None
            if file_name is None
            else SimpleNamespace(
                file_name=file_name,
                file_id=file_id,
            )
        )

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answers.append({"text": text, "reply_markup": reply_markup})

    async def answer_document(self, document, caption: str | None = None) -> None:
        self.documents.append({"document": document, "caption": caption})


class FakeStatusService:
    def __init__(
        self,
        *,
        pending: dict | None,
        prompt: str | None,
        latest_status: StatementStatusSnapshot | None,
        history: list[StatementHistorySnapshot] | None = None,
        details: dict[int, StatementDetailSnapshot] | None = None,
        sources: dict[int, StatementSourceSnapshot] | None = None,
    ) -> None:
        self.pending = pending
        self.prompt = prompt
        self.latest_status = latest_status
        self.history = history or []
        self.details = details or {}
        self.sources = sources or {}

    async def get_pending_clarification(self, telegram_user_id: int):
        assert telegram_user_id == 42
        return self.pending

    async def get_pending_prompt(self, telegram_user_id: int, *, language: str = "en"):
        assert telegram_user_id == 42
        assert language == "en"
        return self.prompt

    async def get_latest_status(self, telegram_user_id: int):
        assert telegram_user_id == 42
        return self.latest_status

    async def get_recent_history(self, telegram_user_id: int, *, limit: int = 5):
        assert telegram_user_id == 42
        assert limit == 5
        return self.history

    async def get_statement_detail(self, telegram_user_id: int, statement_id: int):
        assert telegram_user_id == 42
        return self.details.get(statement_id)

    async def get_statement_source(self, telegram_user_id: int, statement_id: int):
        assert telegram_user_id == 42
        return self.sources.get(statement_id)


@pytest.mark.asyncio
async def test_build_statement_status_reply_returns_pending_resume_text() -> None:
    service = FakeStatusService(
        pending={
            "current_index": 1,
            "items": [{}, {}],
        },
        prompt="Clarification 2 of 2:\nExpense 45000 KZT to 'Arman T.' on 2026-08-13",
        latest_status=StatementStatusSnapshot(
            imported_statement_id=5,
            source_name="Kaspi",
            original_filename="kaspi.csv",
            parse_status="clarification_required",
            imported_at="2026-08-13 10:00",
            parsed_count=2,
            auto_count=0,
            unclear_count=1,
            remaining_clarifications=1,
        ),
    )

    text, pending = await build_statement_status_reply(service, 42)

    assert pending is not None
    assert "Active statement: kaspi.csv" in text
    assert "Resolved so far: 1" in text
    assert "Remaining clarifications: 1" in text
    assert "Clarification 2 of 2" in text


@pytest.mark.asyncio
async def test_build_statement_status_reply_returns_latest_statement_when_idle() -> None:
    service = FakeStatusService(
        pending=None,
        prompt=None,
        latest_status=StatementStatusSnapshot(
            imported_statement_id=8,
            source_name="Halyk",
            original_filename="halyk.xlsx",
            parse_status="completed",
            imported_at="2026-08-13 11:30",
            parsed_count=9,
            auto_count=9,
            unclear_count=0,
            remaining_clarifications=0,
        ),
    )

    text, pending = await build_statement_status_reply(service, 42)

    assert pending is None
    assert "Latest statement: halyk.xlsx" in text
    assert "Status: Completed" in text
    assert "Auto-categorized: 9" in text
    assert "Use /clarify" in text


@pytest.mark.asyncio
async def test_build_statement_callback_reply_returns_resume_view() -> None:
    service = FakeStatusService(
        pending={
            "current_index": 1,
            "items": [{}, {}],
        },
        prompt="Clarification 2 of 2:\nExpense 45000 KZT to 'Arman T.' on 2026-08-13",
        latest_status=StatementStatusSnapshot(
            imported_statement_id=5,
            source_name="Kaspi",
            original_filename="kaspi.csv",
            parse_status="clarification_required",
            imported_at="2026-08-13 10:00",
            parsed_count=2,
            auto_count=0,
            unclear_count=1,
            remaining_clarifications=1,
        ),
    )

    text, markup, notice, show_alert = await build_statement_callback_reply(
        service,
        telegram_user_id=42,
        action="resume",
    )

    assert "Active statement: kaspi.csv" in text
    buttons = _flatten_markup(markup)
    assert any(button.text == "Refresh active statement" for button in buttons)
    assert notice == "Refreshed active clarification"
    assert show_alert is False


@pytest.mark.asyncio
async def test_build_statement_callback_reply_returns_no_pending_resume_view_when_queue_is_empty() -> None:
    service = FakeStatusService(
        pending=None,
        prompt=None,
        latest_status=StatementStatusSnapshot(
            imported_statement_id=8,
            source_name="Halyk",
            original_filename="halyk.xlsx",
            parse_status="completed",
            imported_at="2026-08-13 11:30",
            parsed_count=9,
            auto_count=9,
            unclear_count=0,
            remaining_clarifications=0,
        ),
    )

    text, markup, notice, show_alert = await build_statement_callback_reply(
        service,
        telegram_user_id=42,
        action="resume",
    )

    assert "No pending statement clarifications right now." in text
    assert "Latest statement: halyk.xlsx" in text
    assert markup.inline_keyboard[0][0].text == "Latest statement status"
    assert markup.inline_keyboard[1][0].callback_data == "stmt:status:source-8"
    assert notice == "No pending statement clarification."
    assert show_alert is True


@pytest.mark.asyncio
async def test_build_statement_callback_reply_returns_latest_status_view() -> None:
    service = FakeStatusService(
        pending=None,
        prompt=None,
        latest_status=StatementStatusSnapshot(
            imported_statement_id=8,
            source_name="Halyk",
            original_filename="halyk.xlsx",
            parse_status="completed",
            imported_at="2026-08-13 11:30",
            parsed_count=9,
            auto_count=9,
            unclear_count=0,
            remaining_clarifications=0,
        ),
    )

    text, markup, notice, show_alert = await build_statement_callback_reply(
        service,
        telegram_user_id=42,
        action="latest",
    )

    assert "Latest statement: halyk.xlsx" in text
    assert markup.inline_keyboard[0][0].text == "Latest statement status"
    assert markup.inline_keyboard[1][0].text == "Send source file"
    assert markup.inline_keyboard[1][0].callback_data == "stmt:status:source-8"
    assert notice == "Loaded latest statement status"
    assert show_alert is False


@pytest.mark.asyncio
async def test_build_statement_callback_reply_keeps_latest_source_button_aligned_to_snapshot_when_pending_exists() -> None:
    service = FakeStatusService(
        pending={
            "statement_id": 11,
            "current_index": 0,
            "items": [
                {
                    "suggested_account_type": "business",
                    "suggested_life_sector": "inventory_parts",
                }
            ],
        },
        prompt="Clarification 1 of 1",
        latest_status=StatementStatusSnapshot(
            imported_statement_id=8,
            source_name="Halyk",
            original_filename="halyk.xlsx",
            parse_status="completed",
            imported_at="2026-08-13 11:30",
            parsed_count=9,
            auto_count=9,
            unclear_count=0,
            remaining_clarifications=0,
        ),
    )

    _text, markup, notice, show_alert = await build_statement_callback_reply(
        service,
        telegram_user_id=42,
        action="latest",
        telegram_chat_id=99,
    )

    assert markup.inline_keyboard[0][0].callback_data == "stmt:status:resume"
    assert markup.inline_keyboard[1][0].callback_data == "stmt:status:latest"
    assert markup.inline_keyboard[2][0].callback_data == "stmt:status:source-8"
    assert markup.inline_keyboard[4][0].web_app.url == build_webapp_url(
        tab="quick",
        focus="clarify",
        statement_id=11,
        telegram_user_id=42,
        telegram_chat_id=99,
    )
    assert notice == "Loaded latest statement status"
    assert show_alert is False


@pytest.mark.asyncio
async def test_build_statement_callback_reply_returns_history_view() -> None:
    service = FakeStatusService(
        pending=None,
        prompt=None,
        latest_status=StatementStatusSnapshot(
            imported_statement_id=8,
            source_name="Halyk",
            original_filename="halyk.xlsx",
            parse_status="completed",
            imported_at="2026-08-13 11:30",
            parsed_count=9,
            auto_count=9,
            unclear_count=0,
            remaining_clarifications=0,
        ),
        history=[
            StatementHistorySnapshot(
                imported_statement_id=8,
                source_name="Halyk",
                original_filename="halyk.xlsx",
                parse_status="completed",
                imported_at="2026-08-13 11:30",
                parsed_count=9,
                auto_count=9,
                unclear_count=0,
                remaining_clarifications=0,
            ),
            StatementHistorySnapshot(
                imported_statement_id=7,
                source_name="Kaspi",
                original_filename="kaspi.csv",
                parse_status="clarification_required",
                imported_at="2026-08-13 10:00",
                parsed_count=2,
                auto_count=0,
                unclear_count=1,
                remaining_clarifications=1,
            ),
        ],
    )

    text, markup, notice, show_alert = await build_statement_callback_reply(
        service,
        telegram_user_id=42,
        action="history",
    )

    assert "Recent statement imports:" in text
    assert "1. halyk.xlsx" in text
    assert "2. kaspi.csv" in text
    assert "Reply `detail 1` to open an import or `source 1` to receive its original file." in text
    assert "You can also use the buttons below." in text
    assert markup.inline_keyboard[0][0].callback_data == "stmt:status:detail-8"
    assert markup.inline_keyboard[0][1].text == "Source"
    assert markup.inline_keyboard[0][1].callback_data == "stmt:status:source-8"
    assert markup.inline_keyboard[1][0].callback_data == "stmt:status:detail-7"
    assert markup.inline_keyboard[1][1].callback_data == "stmt:status:source-7"
    assert notice == "Loaded recent statement imports"
    assert show_alert is False


@pytest.mark.asyncio
async def test_build_statement_callback_reply_returns_detail_view() -> None:
    service = FakeStatusService(
        pending={
            "statement_id": 8,
            "current_index": 0,
            "items": [
                {
                    "transaction_type": "expense",
                    "amount": "45000",
                    "counterparty": "Arman T.",
                    "statement_date": "2026-08-11",
                    "description": "P2P transfer to supplier",
                    "reason": "This looks like a person-to-person transfer that still needs your intent.",
                    "suggested_account_type": "business",
                    "suggested_life_sector": "inventory_parts",
                    "matched_rules": [
                        {
                            "account_type": "business",
                            "life_sector": "inventory_parts",
                            "explanation": "Arman T. is usually a supplier payment.",
                        }
                    ],
                }
            ],
        },
        prompt="Clarification 1 of 1",
        latest_status=StatementStatusSnapshot(
            imported_statement_id=8,
            source_name="Halyk",
            original_filename="halyk.xlsx",
            parse_status="clarification_required",
            imported_at="2026-08-13 11:30",
            parsed_count=9,
            auto_count=8,
            unclear_count=1,
            remaining_clarifications=1,
        ),
        details={
            8: StatementDetailSnapshot(
                imported_statement_id=8,
                source_name="Halyk",
                original_filename="halyk.xlsx",
                parse_status="clarification_required",
                imported_at="2026-08-13 11:30",
                parsed_count=9,
                auto_count=8,
                unclear_count=1,
                remaining_clarifications=1,
                note="parsed=9 auto=8 unclear=1",
                storage_kind="local_file",
                file_available=True,
                is_active=True,
                raw_line_count=3,
                raw_preview="date,amount,counterparty\n2026-08-10,150000,Client LLP\n2026-08-11,-45000,Arman T.",
                raw_preview_truncated=False,
            )
        },
    )

    text, markup, notice, show_alert = await build_statement_callback_reply(
        service,
        telegram_user_id=42,
        action="detail-8",
    )

    assert "Statement import detail: halyk.xlsx" in text
    assert "Active clarification queue: 1 still open" in text
    assert "Resolved so far: 0" in text
    assert "Remaining clarifications: 1" in text
    assert "Expense 45000 KZT to 'Arman T.' on 2026-08-11" in text
    assert "Statement note: P2P transfer to supplier" in text
    assert "Reason: This looks like a person-to-person transfer that still needs your intent." in text
    assert "Learned precedents:" in text
    assert "- Business / Inventory / Parts: Arman T. is usually a supplier payment." in text
    assert "Suggested quick choice: Business / Inventory / Parts" in text
    assert "Fastest confirm now: `1` = Learned: Business / Inventory / Parts" in text
    assert "Shortcut: reply `same as before`" in text
    assert "Storage: local file available" in text
    assert "Raw preview: showing 3 of 3 lines" in text
    assert "1. date,amount,counterparty" in text
    assert markup.inline_keyboard[0][0].callback_data == "stmt:status:resume"
    assert markup.inline_keyboard[1][0].callback_data == "stmt:status:source-8"
    assert markup.inline_keyboard[1][0].text == "Send source file"
    assert markup.inline_keyboard[2][0].callback_data == "stmt:status:history"
    assert notice == "Loaded statement import detail"
    assert show_alert is False


@pytest.mark.asyncio
async def test_send_statement_source_message_streams_local_file(tmp_path) -> None:
    source_path = tmp_path / "halyk.xlsx"
    source_path.write_bytes(b"stub-xlsx")
    service = FakeStatusService(
        pending=None,
        prompt=None,
        latest_status=None,
        sources={
            8: StatementSourceSnapshot(
                filename="halyk.xlsx",
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                file_path=source_path,
            )
        },
    )
    message = FakeMessage()

    notice, show_alert = await _send_statement_source_message(
        message,
        service,
        telegram_user_id=42,
        statement_id=8,
    )

    assert notice == "Sent statement source: halyk.xlsx"
    assert show_alert is False
    assert message.documents[0]["caption"] == "Original statement source: halyk.xlsx"
    assert message.documents[0]["document"].filename == "halyk.xlsx"
    assert Path(message.documents[0]["document"].path) == source_path


@pytest.mark.asyncio
async def test_send_statement_source_message_falls_back_to_buffered_text_attachment() -> None:
    service = FakeStatusService(
        pending=None,
        prompt=None,
        latest_status=None,
        sources={
            8: StatementSourceSnapshot(
                filename="statement-import.txt",
                media_type="text/plain; charset=utf-8",
                content=b"2026-08-12,-45000,Arman T.\n",
            )
        },
    )
    message = FakeMessage()

    notice, show_alert = await _send_statement_source_message(
        message,
        service,
        telegram_user_id=42,
        statement_id=8,
    )

    assert notice == "Sent statement source: statement-import.txt"
    assert show_alert is False
    assert message.documents[0]["caption"] == "Original statement source: statement-import.txt"
    assert message.documents[0]["document"].filename == "statement-import.txt"
    assert message.documents[0]["document"].data == b"2026-08-12,-45000,Arman T.\n"


@pytest.mark.asyncio
async def test_handle_statement_document_replies_for_unsupported_upload() -> None:
    message = FakeMessage(file_name="notes.txt")
    session_factory = DummySessionFactory()

    handled = await handle_statement_document(session_factory, message)

    assert handled is True
    assert message.answers == [
        {
            "text": (
                "This document format is not supported for bank statement import yet. "
                "Send PDF, CSV, XLSX, or XLS, or paste raw statement lines here."
            ),
            "reply_markup": None,
        }
    ]
    assert session_factory.session.commit_calls == 0


@pytest.mark.asyncio
async def test_handle_statement_document_imports_supported_file(monkeypatch, tmp_path) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "local_storage_path", str(tmp_path), raising=False)

    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def import_file(self, **kwargs):
            assert kwargs["telegram_user_id"] == 42
            assert kwargs["telegram_chat_id"] == 99
            assert kwargs["original_filename"] == "statement.csv"
            assert kwargs["file_path"].exists()
            assert kwargs["language"] == "en"
            return SimpleNamespace(
                summary_message="Processing bank statement (2 items)...",
                prompt_message="Clarification 1 of 1",
            )

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

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=7,
                source_name="Kaspi",
                original_filename="statement.csv",
                parse_status="clarification_required",
                imported_at="2026-08-13 10:00",
                parsed_count=2,
                auto_count=1,
                unclear_count=1,
                remaining_clarifications=1,
            )

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)

    message = FakeMessage(file_name="statement.csv", file_id="doc-777")
    session_factory = DummySessionFactory()

    handled = await handle_statement_document(session_factory, message)

    assert handled is True
    assert message.bot.downloads
    assert message.bot.downloads[0][1].exists()
    assert message.bot.downloads[0][1].name.startswith("doc-777_")
    assert message.bot.downloads[0][1].suffix == ".csv"
    assert session_factory.session.commit_calls == 1
    assert message.answers[0]["text"] == "Processing bank statement (2 items)..."
    assert message.answers[1]["text"] == "Clarification 1 of 1"
    assert message.answers[1]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_handle_statement_document_keeps_active_queue_when_new_file_arrives(monkeypatch, tmp_path) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "local_storage_path", str(tmp_path), raising=False)

    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def import_file(self, **kwargs):
            raise ActiveStatementImportConflictError(
                statement_name="active.csv",
                remaining_clarifications=1,
            )

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

        async def get_pending_prompt(self, telegram_user_id: int, *, language: str = "en"):
            assert telegram_user_id == 42
            assert language == "en"
            return "Clarification 1 of 1"

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=13,
                source_name="Kaspi",
                original_filename="active.csv",
                parse_status="clarification_required",
                imported_at="2026-08-13 13:00",
                parsed_count=2,
                auto_count=1,
                unclear_count=1,
                remaining_clarifications=1,
            )

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)

    message = FakeMessage(file_name="incoming.csv", file_id="doc-999")
    session_factory = DummySessionFactory()

    handled = await handle_statement_document(session_factory, message)

    assert handled is True
    assert message.bot.downloads
    assert not message.bot.downloads[0][1].exists()
    assert session_factory.session.commit_calls == 0
    assert message.answers[0]["text"] == (
        'Finish the active clarification for "active.csv" before importing a new statement. '
        "Remaining clarifications: 1."
    )
    assert "Active statement: active.csv" in str(message.answers[1]["text"])
    assert "Clarification 1 of 1" in str(message.answers[1]["text"])
    assert message.answers[1]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_handle_statement_document_cleans_up_download_when_import_fails(monkeypatch, tmp_path) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "local_storage_path", str(tmp_path), raising=False)

    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def import_file(self, **kwargs):
            raise RuntimeError("Classifier unavailable")

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)

    message = FakeMessage(file_name="broken.csv", file_id="doc-444")
    session_factory = DummySessionFactory()

    handled = await handle_statement_document(session_factory, message)

    assert handled is True
    assert message.bot.downloads
    assert not message.bot.downloads[0][1].exists()
    assert session_factory.session.commit_calls == 0
    assert message.answers == [{"text": message.answers[0]["text"], "reply_markup": None}]
    assert "Could not import this statement right now." in str(message.answers[0]["text"])
    assert "Classifier unavailable" in str(message.answers[0]["text"])


@pytest.mark.asyncio
async def test_try_handle_statement_text_processes_pending_clarification(monkeypatch) -> None:
    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def process_clarification_text(self, **kwargs):
            assert kwargs["answer_text"] == "business parts"
            assert kwargs["language"] == "en"
            return "Saved. Next clarification 2 of 2"

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

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=7,
                source_name="Kaspi",
                original_filename="statement.csv",
                parse_status="clarification_required",
                imported_at="2026-08-13 10:00",
                parsed_count=2,
                auto_count=1,
                unclear_count=1,
                remaining_clarifications=1,
            )

        async def import_text(self, **kwargs):
            raise AssertionError("import_text should not run when clarification is pending")

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)

    message = FakeMessage(text="business parts")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is True
    assert session_factory.session.commit_calls == 1
    assert message.answers[0]["text"] == "Saved. Next clarification 2 of 2"
    assert message.answers[0]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_try_handle_statement_text_accepts_numeric_quick_choice(monkeypatch) -> None:
    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def process_clarification_text(self, **kwargs):
            assert kwargs["answer_text"] == "1"
            assert kwargs["language"] == "en"
            return "Saved. Next clarification 2 of 2"

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

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=7,
                source_name="Kaspi",
                original_filename="statement.csv",
                parse_status="clarification_required",
                imported_at="2026-08-13 10:00",
                parsed_count=2,
                auto_count=1,
                unclear_count=1,
                remaining_clarifications=1,
            )

        async def import_text(self, **kwargs):
            raise AssertionError("import_text should not run when clarification is pending")

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)

    message = FakeMessage(text="1")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is True
    assert session_factory.session.commit_calls == 1
    assert message.answers[0]["text"] == "Saved. Next clarification 2 of 2"
    assert message.answers[0]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_try_handle_statement_text_rehydrates_when_clarification_was_already_resolved_elsewhere(monkeypatch) -> None:
    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def process_clarification_text(self, **kwargs):
            assert kwargs["answer_text"] == "business parts"
            return None

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

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=15,
                source_name="Kaspi",
                original_filename="resolved.csv",
                parse_status="completed",
                imported_at="2026-08-13 13:40",
                parsed_count=2,
                auto_count=2,
                unclear_count=0,
                remaining_clarifications=0,
            )

        async def import_text(self, **kwargs):
            raise AssertionError("import_text should not run after a stale clarification reply")

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)

    message = FakeMessage(text="business parts")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is True
    assert session_factory.session.commit_calls == 0
    assert "No pending statement clarifications right now." in str(message.answers[0]["text"])
    assert "Latest statement: resolved.csv" in str(message.answers[0]["text"])
    assert message.answers[0]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_try_handle_statement_text_blocks_new_statement_lines_while_clarification_is_active(monkeypatch) -> None:
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

        async def get_pending_prompt(self, telegram_user_id: int, *, language: str = "en"):
            assert telegram_user_id == 42
            assert language == "en"
            return "Clarification 1 of 1"

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=14,
                source_name="Kaspi",
                original_filename="active.csv",
                parse_status="clarification_required",
                imported_at="2026-08-13 13:20",
                parsed_count=2,
                auto_count=1,
                unclear_count=1,
                remaining_clarifications=1,
            )

        async def process_clarification_text(self, **kwargs):
            raise AssertionError("process_clarification_text should not run for a new statement paste")

        async def import_text(self, **kwargs):
            raise AssertionError("import_text should not run while a clarification queue is active")

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)

    message = FakeMessage(text="2026-08-10 Client LLP +150000\n2026-08-11 Arman T. -45000")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is True
    assert session_factory.session.commit_calls == 0
    assert message.answers[0]["text"] == (
        'Finish the active clarification for "active.csv" before importing a new statement. '
        "Remaining clarifications: 1."
    )
    assert "Active statement: active.csv" in str(message.answers[1]["text"])
    assert "Clarification 1 of 1" in str(message.answers[1]["text"])
    assert message.answers[1]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_try_handle_statement_text_allows_quick_log_to_fall_through_while_clarification_is_active(monkeypatch) -> None:
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
            raise AssertionError("process_clarification_text should not run for a quick log")

        async def import_text(self, **kwargs):
            raise AssertionError("import_text should not run while a clarification queue is active")

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)

    message = FakeMessage(text="17000 kassa")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is False
    assert session_factory.session.commit_calls == 0
    assert message.answers == []


@pytest.mark.asyncio
async def test_try_handle_statement_text_allows_generic_chat_to_fall_through_while_clarification_is_active(monkeypatch) -> None:
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
            raise AssertionError("process_clarification_text should not run for generic chat")

        async def import_text(self, **kwargs):
            raise AssertionError("import_text should not run for generic chat")

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)

    message = FakeMessage(text="Need help with margins")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is False
    assert session_factory.session.commit_calls == 0
    assert message.answers == []


@pytest.mark.asyncio
async def test_try_handle_statement_text_routes_history_shortcut_during_clarification(monkeypatch) -> None:
    callback_calls: list[tuple[int, int | None, str, str]] = []

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
            raise AssertionError("process_clarification_text should not run for history shortcut")

        async def import_text(self, **kwargs):
            raise AssertionError("import_text should not run for history shortcut")

    async def fake_build_statement_callback_reply(
        service,
        *,
        telegram_user_id: int,
        telegram_chat_id: int | None = None,
        action: str,
        lang: str = "en",
    ):
        assert isinstance(service, FakeStatementImportService)
        callback_calls.append((telegram_user_id, telegram_chat_id, action, lang))
        return ("Recent statement imports:", None, "Loaded recent statement imports", False)

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)
    monkeypatch.setattr(statement_handlers, "build_statement_callback_reply", fake_build_statement_callback_reply)

    message = FakeMessage(text="history")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is True
    assert callback_calls == [(42, 99, "history", "en")]
    assert session_factory.session.commit_calls == 0
    assert message.answers == [{"text": "Recent statement imports:", "reply_markup": None}]


@pytest.mark.asyncio
async def test_try_handle_statement_text_routes_detail_shortcut_from_history_index(monkeypatch) -> None:
    callback_calls: list[tuple[int, int | None, str, str]] = []

    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def get_pending_clarification(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return None

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=8,
                source_name="Halyk",
                original_filename="halyk.xlsx",
                parse_status="completed",
                imported_at="2026-08-13 11:30",
                parsed_count=9,
                auto_count=9,
                unclear_count=0,
                remaining_clarifications=0,
            )

        async def get_recent_history(self, telegram_user_id: int, *, limit: int = 5):
            assert telegram_user_id == 42
            assert limit == 5
            return [
                StatementHistorySnapshot(
                    imported_statement_id=8,
                    source_name="Halyk",
                    original_filename="halyk.xlsx",
                    parse_status="completed",
                    imported_at="2026-08-13 11:30",
                    parsed_count=9,
                    auto_count=9,
                    unclear_count=0,
                    remaining_clarifications=0,
                ),
                StatementHistorySnapshot(
                    imported_statement_id=7,
                    source_name="Kaspi",
                    original_filename="kaspi.csv",
                    parse_status="clarification_required",
                    imported_at="2026-08-13 10:00",
                    parsed_count=2,
                    auto_count=0,
                    unclear_count=1,
                    remaining_clarifications=1,
                ),
            ]

        async def process_clarification_text(self, **kwargs):
            raise AssertionError("process_clarification_text should not run for detail shortcut")

        async def import_text(self, **kwargs):
            raise AssertionError("import_text should not run for detail shortcut")

    async def fake_build_statement_callback_reply(
        service,
        *,
        telegram_user_id: int,
        telegram_chat_id: int | None = None,
        action: str,
        lang: str = "en",
    ):
        assert isinstance(service, FakeStatementImportService)
        callback_calls.append((telegram_user_id, telegram_chat_id, action, lang))
        return ("Statement import detail: kaspi.csv", None, "Loaded statement import detail", False)

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)
    monkeypatch.setattr(statement_handlers, "build_statement_callback_reply", fake_build_statement_callback_reply)

    message = FakeMessage(text="detail 2")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is True
    assert callback_calls == [(42, 99, "detail-7", "en")]
    assert session_factory.session.commit_calls == 0
    assert message.answers == [{"text": "Statement import detail: kaspi.csv", "reply_markup": None}]


@pytest.mark.asyncio
async def test_try_handle_statement_text_routes_detail_shortcut_from_spoken_history_index(monkeypatch) -> None:
    callback_calls: list[tuple[int, int | None, str, str]] = []

    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def get_pending_clarification(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return None

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=8,
                source_name="Halyk",
                original_filename="halyk.xlsx",
                parse_status="completed",
                imported_at="2026-08-13 11:30",
                parsed_count=9,
                auto_count=9,
                unclear_count=0,
                remaining_clarifications=0,
            )

        async def get_recent_history(self, telegram_user_id: int, *, limit: int = 5):
            assert telegram_user_id == 42
            assert limit == 5
            return [
                StatementHistorySnapshot(
                    imported_statement_id=8,
                    source_name="Halyk",
                    original_filename="halyk.xlsx",
                    parse_status="completed",
                    imported_at="2026-08-13 11:30",
                    parsed_count=9,
                    auto_count=9,
                    unclear_count=0,
                    remaining_clarifications=0,
                ),
                StatementHistorySnapshot(
                    imported_statement_id=7,
                    source_name="Kaspi",
                    original_filename="kaspi.csv",
                    parse_status="clarification_required",
                    imported_at="2026-08-13 10:00",
                    parsed_count=2,
                    auto_count=0,
                    unclear_count=1,
                    remaining_clarifications=1,
                ),
            ]

        async def process_clarification_text(self, **kwargs):
            raise AssertionError("process_clarification_text should not run for detail shortcut")

        async def import_text(self, **kwargs):
            raise AssertionError("import_text should not run for detail shortcut")

    async def fake_build_statement_callback_reply(
        service,
        *,
        telegram_user_id: int,
        telegram_chat_id: int | None = None,
        action: str,
        lang: str = "en",
    ):
        assert isinstance(service, FakeStatementImportService)
        callback_calls.append((telegram_user_id, telegram_chat_id, action, lang))
        return ("Statement import detail: kaspi.csv", None, "Loaded statement import detail", False)

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)
    monkeypatch.setattr(statement_handlers, "build_statement_callback_reply", fake_build_statement_callback_reply)

    message = FakeMessage(text="show second import")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is True
    assert callback_calls == [(42, 99, "detail-7", "en")]
    assert session_factory.session.commit_calls == 0
    assert message.answers == [{"text": "Statement import detail: kaspi.csv", "reply_markup": None}]


@pytest.mark.asyncio
async def test_try_handle_statement_text_routes_reference_first_latest_detail_shortcut(monkeypatch) -> None:
    callback_calls: list[tuple[int, int | None, str, str]] = []

    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def get_pending_clarification(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return None

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=8,
                source_name="Halyk",
                original_filename="halyk.xlsx",
                parse_status="completed",
                imported_at="2026-08-13 11:30",
                parsed_count=9,
                auto_count=9,
                unclear_count=0,
                remaining_clarifications=0,
            )

        async def process_clarification_text(self, **kwargs):
            raise AssertionError("process_clarification_text should not run for detail shortcut")

        async def import_text(self, **kwargs):
            raise AssertionError("import_text should not run for detail shortcut")

    async def fake_build_statement_callback_reply(
        service,
        *,
        telegram_user_id: int,
        telegram_chat_id: int | None = None,
        action: str,
        lang: str = "en",
    ):
        assert isinstance(service, FakeStatementImportService)
        callback_calls.append((telegram_user_id, telegram_chat_id, action, lang))
        return ("Statement import detail: halyk.xlsx", None, "Loaded statement import detail", False)

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)
    monkeypatch.setattr(statement_handlers, "build_statement_callback_reply", fake_build_statement_callback_reply)

    message = FakeMessage(text="please latest statement detail")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is True
    assert callback_calls == [(42, 99, "detail-8", "en")]
    assert session_factory.session.commit_calls == 0
    assert message.answers == [{"text": "Statement import detail: halyk.xlsx", "reply_markup": None}]


@pytest.mark.asyncio
async def test_try_handle_statement_text_routes_source_shortcut_to_active_statement(monkeypatch) -> None:
    source_calls: list[tuple[int, str]] = []

    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def get_pending_clarification(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return {
                "statement_id": 11,
                "current_index": 0,
                "items": [
                    {
                        "suggested_account_type": "business",
                        "suggested_life_sector": "inventory_parts",
                    }
                ],
            }

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=11,
                source_name="Kaspi",
                original_filename="active.csv",
                parse_status="clarification_required",
                imported_at="2026-08-13 12:20",
                parsed_count=3,
                auto_count=2,
                unclear_count=1,
                remaining_clarifications=1,
            )

        async def process_clarification_text(self, **kwargs):
            raise AssertionError("process_clarification_text should not run for source shortcut")

        async def import_text(self, **kwargs):
            raise AssertionError("import_text should not run for source shortcut")

    async def fake_send_statement_source_message(
        message,
        service,
        *,
        telegram_user_id: int,
        statement_id: int,
        lang: str = "en",
    ):
        assert isinstance(service, FakeStatementImportService)
        assert telegram_user_id == 42
        assert lang == "en"
        source_calls.append((statement_id, lang))
        message.documents.append({"document": "active.csv", "caption": "Original statement source: active.csv"})
        return ("Sent statement source: active.csv", False)

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)
    monkeypatch.setattr(statement_handlers, "_send_statement_source_message", fake_send_statement_source_message)

    message = FakeMessage(text="send source file")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is True
    assert source_calls == [(11, "en")]
    assert session_factory.session.commit_calls == 0
    assert message.answers == []
    assert message.documents == [{"document": "active.csv", "caption": "Original statement source: active.csv"}]


@pytest.mark.asyncio
async def test_try_handle_statement_text_imports_statement_lines(monkeypatch) -> None:
    pending_calls = 0

    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def process_clarification_text(self, **kwargs):
            return None

        async def import_text(self, **kwargs):
            assert "2026-08-10 Client LLP +150000" in kwargs["raw_text"]
            assert kwargs["language"] == "en"
            return SimpleNamespace(
                summary_message="Processing bank statement (1 items)...",
                prompt_message="Clarification 1 of 1",
            )

        async def get_pending_clarification(self, telegram_user_id: int):
            nonlocal pending_calls
            assert telegram_user_id == 42
            pending_calls += 1
            if pending_calls == 1:
                return None
            return {
                "current_index": 0,
                "items": [
                    {
                        "suggested_account_type": "business",
                        "suggested_life_sector": "sales_income",
                    }
                ],
            }

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=9,
                source_name="Kaspi",
                original_filename="import.txt",
                parse_status="clarification_required",
                imported_at="2026-08-13 11:15",
                parsed_count=1,
                auto_count=0,
                unclear_count=1,
                remaining_clarifications=1,
            )

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)

    message = FakeMessage(text="2026-08-10 Client LLP +150000")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is True
    assert session_factory.session.commit_calls == 1
    assert [entry["text"] for entry in message.answers] == [
        "Processing bank statement (1 items)...",
        "Clarification 1 of 1",
    ]
    assert message.answers[1]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_try_handle_statement_text_rehydrates_conflict_state_when_import_slot_is_taken(monkeypatch) -> None:
    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def process_clarification_text(self, **kwargs):
            return None

        async def import_text(self, **kwargs):
            raise ActiveStatementImportConflictError(statement_name="active.csv", remaining_clarifications=1)

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

        async def get_pending_prompt(self, telegram_user_id: int, *, language: str = "en"):
            assert telegram_user_id == 42
            assert language == "en"
            return "Clarification 1 of 1"

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=19,
                source_name="Kaspi",
                original_filename="active.csv",
                parse_status="clarification_required",
                imported_at="2026-08-13 14:10",
                parsed_count=2,
                auto_count=1,
                unclear_count=1,
                remaining_clarifications=1,
            )

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)

    message = FakeMessage(text="2026-08-12 Kaspi Incoming +99000")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is True
    assert session_factory.session.commit_calls == 0
    assert message.answers[0]["text"] == (
        'Finish the active clarification for "active.csv" before importing a new statement. '
        "Remaining clarifications: 1."
    )
    assert "Active statement: active.csv" in str(message.answers[1]["text"])
    assert "Clarification 1 of 1" in str(message.answers[1]["text"])
    assert message.answers[1]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_try_handle_statement_text_returns_localized_failure_when_import_crashes(monkeypatch) -> None:
    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def get_pending_clarification(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return None

        async def process_clarification_text(self, **kwargs):
            return None

        async def import_text(self, **kwargs):
            raise RuntimeError("Statement parser unavailable.")

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)

    message = FakeMessage(text="2026-08-10 Client LLP +150000")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is True
    assert session_factory.session.commit_calls == 0
    assert message.answers[0]["text"] == (
        "Could not import this statement right now. Send PDF, CSV, XLSX, or XLS, or paste raw statement lines here. "
        "Details: Statement parser unavailable."
    )


@pytest.mark.asyncio
async def test_try_handle_statement_text_returns_localized_failure_when_clarification_crashes(monkeypatch) -> None:
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
            raise RuntimeError("Classifier unavailable.")

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)

    message = FakeMessage(text="business parts")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is True
    assert session_factory.session.commit_calls == 0
    assert message.answers[0]["text"] == (
        "Could not save this clarification right now. Please try again. Details: Classifier unavailable."
    )


@pytest.mark.asyncio
async def test_try_handle_statement_text_routes_same_as_before_to_clarification(monkeypatch) -> None:
    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def get_pending_clarification(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return {
                "current_index": 0,
                "items": [
                    {
                        "matched_rules": [
                            {
                                "match_key": "arman t",
                                "account_type": "business",
                                "life_sector": "inventory_parts",
                                "explanation": "Arman T. is usually a supplier payment.",
                            }
                        ]
                    }
                ],
            }

        async def process_clarification_text(self, **kwargs):
            assert kwargs["answer_text"] == "same as before"
            return "Statement import complete. All unclear items were resolved and saved into memory."

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=11,
                source_name="Kaspi",
                original_filename="final.csv",
                parse_status="completed",
                imported_at="2026-08-13 12:20",
                parsed_count=3,
                auto_count=3,
                unclear_count=0,
                remaining_clarifications=0,
            )

        async def import_text(self, **kwargs):
            raise AssertionError("import_text should not run when clarification text produced a reply")

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)

    message = FakeMessage(text="same as before")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is True
    assert session_factory.session.commit_calls == 1
    assert "Statement import complete." in str(message.answers[0]["text"])


@pytest.mark.asyncio
async def test_try_handle_statement_text_routes_supplier_payment_to_clarification(monkeypatch) -> None:
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
            assert kwargs["answer_text"] == "supplier payment"
            return "Statement import complete. All unclear items were resolved and saved into memory."

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=11,
                source_name="Kaspi",
                original_filename="final.csv",
                parse_status="completed",
                imported_at="2026-08-13 12:20",
                parsed_count=3,
                auto_count=3,
                unclear_count=0,
                remaining_clarifications=0,
            )

        async def import_text(self, **kwargs):
            raise AssertionError("import_text should not run when clarification text produced a reply")

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)

    message = FakeMessage(text="supplier payment")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is True
    assert session_factory.session.commit_calls == 1
    assert "Statement import complete." in str(message.answers[0]["text"])


@pytest.mark.asyncio
async def test_try_handle_statement_text_routes_russian_inventory_reply_to_clarification(monkeypatch) -> None:
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
            assert kwargs["answer_text"] == "товар для бизнеса"
            return "Statement import complete. All unclear items were resolved and saved into memory."

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=11,
                source_name="Kaspi",
                original_filename="final.csv",
                parse_status="completed",
                imported_at="2026-08-13 12:20",
                parsed_count=3,
                auto_count=3,
                unclear_count=0,
                remaining_clarifications=0,
            )

        async def import_text(self, **kwargs):
            raise AssertionError("import_text should not run when clarification text produced a reply")

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)

    message = FakeMessage(text="товар для бизнеса")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is True
    assert session_factory.session.commit_calls == 1
    assert "Statement import complete." in str(message.answers[0]["text"])


@pytest.mark.asyncio
async def test_try_handle_statement_text_sends_completion_status_when_last_clarification_is_saved(monkeypatch) -> None:
    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def process_clarification_text(self, **kwargs):
            assert kwargs["answer_text"] == "business sales"
            return "Statement import complete. All unclear items were resolved and saved into memory."

        async def get_pending_clarification(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return None

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=11,
                source_name="Kaspi",
                original_filename="final.csv",
                parse_status="completed",
                imported_at="2026-08-13 12:20",
                parsed_count=3,
                auto_count=3,
                unclear_count=0,
                remaining_clarifications=0,
            )

        async def import_text(self, **kwargs):
            raise AssertionError("import_text should not run when clarification text produced a reply")

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)

    message = FakeMessage(text="business sales")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is True
    assert session_factory.session.commit_calls == 1
    assert "Statement import complete." in str(message.answers[0]["text"])
    assert "Latest statement: final.csv" in str(message.answers[0]["text"])
    assert "Use the buttons below to review status or open the Mini App." in str(message.answers[0]["text"])
    assert message.answers[0]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_try_handle_statement_text_shows_latest_status_when_import_needs_no_clarification(monkeypatch) -> None:
    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def process_clarification_text(self, **kwargs):
            return None

        async def import_text(self, **kwargs):
            return SimpleNamespace(
                summary_message="Processing bank statement (1 items)...",
                prompt_message=None,
            )

        async def get_pending_clarification(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return None

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=12,
                source_name="Halyk",
                original_filename="clean.csv",
                parse_status="completed",
                imported_at="2026-08-13 12:35",
                parsed_count=1,
                auto_count=1,
                unclear_count=0,
                remaining_clarifications=0,
            )

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)

    message = FakeMessage(text="2026-08-13 Client LLP +150000")
    session_factory = DummySessionFactory()

    handled = await try_handle_statement_text(session_factory, message)

    assert handled is True
    assert [entry["text"] for entry in message.answers] == [
        "Processing bank statement (1 items)...",
        (
            "Latest statement: clean.csv\n"
            "Source: Halyk\n"
            "Imported: 2026-08-13 12:35\n"
            "Status: Completed\n"
            "Parsed items: 1\n"
            "Auto-categorized: 1\n"
            "Needs clarification: 0\n\n"
            "Send a bank statement as PDF, CSV, XLSX, or XLS, or paste raw statement lines here.\n"
            "Use /clarify any time to resume the current clarification loop.\n"
            "Use /app or the Mini App button below to inspect balances, cashflow, and pending questions."
        ),
    ]
    assert message.answers[1]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_try_handle_statement_voice_returns_local_fallback_when_transcription_unavailable(monkeypatch, tmp_path) -> None:
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

    class FailingSpeechAdapter:
        def transcribe(self, audio_path: Path) -> str:
            raise RuntimeError(f"speech stack missing for {audio_path.name}")

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)
    monkeypatch.setattr(statement_handlers, "SpeechAdapter", FailingSpeechAdapter)

    message = FakeMessage()
    session_factory = DummySessionFactory()
    audio_path = tmp_path / "clarification.ogg"
    audio_path.write_text("stub", encoding="utf-8")

    handled = await try_handle_statement_voice(session_factory, message, audio_path)

    assert handled is True
    assert session_factory.session.commit_calls == 0
    assert "Voice clarification is unavailable locally right now." in str(message.answers[0]["text"])
    assert "Please reply in text or install the local speech stack." in str(message.answers[0]["text"])


@pytest.mark.asyncio
async def test_try_handle_statement_voice_rehydrates_when_clarification_was_already_resolved_elsewhere(
    monkeypatch, tmp_path
) -> None:
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
            assert kwargs["answer_text"] == "business parts"
            return None

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=16,
                source_name="Kaspi",
                original_filename="voice-resolved.csv",
                parse_status="completed",
                imported_at="2026-08-13 13:45",
                parsed_count=3,
                auto_count=3,
                unclear_count=0,
                remaining_clarifications=0,
            )

    class FakeSpeechAdapter:
        def transcribe(self, audio_path: Path) -> str:
            assert audio_path.name == "stale-clarification.ogg"
            return "business parts"

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)
    monkeypatch.setattr(statement_handlers, "SpeechAdapter", FakeSpeechAdapter)

    message = FakeMessage()
    session_factory = DummySessionFactory()
    audio_path = tmp_path / "stale-clarification.ogg"
    audio_path.write_text("stub", encoding="utf-8")

    handled = await try_handle_statement_voice(session_factory, message, audio_path)

    assert handled is True
    assert session_factory.session.commit_calls == 0
    assert "No pending statement clarifications right now." in str(message.answers[0]["text"])
    assert "Latest statement: voice-resolved.csv" in str(message.answers[0]["text"])
    assert message.answers[0]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_try_handle_statement_voice_allows_quick_log_transcript_to_fall_through_while_clarification_is_active(
    monkeypatch, tmp_path
) -> None:
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
            raise AssertionError("process_clarification_text should not run for a quick log transcript")

    class FakeSpeechAdapter:
        def transcribe(self, audio_path: Path) -> str:
            assert audio_path.name == "quick-log.ogg"
            return "17000 kassa"

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)
    monkeypatch.setattr(statement_handlers, "SpeechAdapter", FakeSpeechAdapter)

    message = FakeMessage()
    session_factory = DummySessionFactory()
    audio_path = tmp_path / "quick-log.ogg"
    audio_path.write_text("stub", encoding="utf-8")

    handled = await try_handle_statement_voice(session_factory, message, audio_path)

    assert handled is False
    assert session_factory.session.commit_calls == 0
    assert message.answers == []


@pytest.mark.asyncio
async def test_try_handle_statement_voice_allows_generic_chat_transcript_to_fall_through_while_clarification_is_active(
    monkeypatch, tmp_path
) -> None:
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
            raise AssertionError("process_clarification_text should not run for generic voice chat")

    class FakeSpeechAdapter:
        def transcribe(self, audio_path: Path) -> str:
            assert audio_path.name == "generic-chat.ogg"
            return "Need help with margins"

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)
    monkeypatch.setattr(statement_handlers, "SpeechAdapter", FakeSpeechAdapter)

    message = FakeMessage()
    session_factory = DummySessionFactory()
    audio_path = tmp_path / "generic-chat.ogg"
    audio_path.write_text("stub", encoding="utf-8")

    handled = await try_handle_statement_voice(session_factory, message, audio_path)

    assert handled is False
    assert session_factory.session.commit_calls == 0
    assert message.answers == []


@pytest.mark.asyncio
async def test_try_handle_statement_voice_routes_kazakh_inventory_reply_to_clarification(monkeypatch, tmp_path) -> None:
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
            assert kwargs["answer_text"] == "жабдық бизнеске"
            return "Statement import complete. All unclear items were resolved and saved into memory."

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=16,
                source_name="Kaspi",
                original_filename="voice-resolved.csv",
                parse_status="completed",
                imported_at="2026-08-13 13:45",
                parsed_count=3,
                auto_count=3,
                unclear_count=0,
                remaining_clarifications=0,
            )

    class FakeSpeechAdapter:
        def transcribe(self, audio_path: Path) -> str:
            assert audio_path.name == "kazakh-clarification.ogg"
            return "жабдық бизнеске"

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)
    monkeypatch.setattr(statement_handlers, "SpeechAdapter", FakeSpeechAdapter)

    message = FakeMessage()
    session_factory = DummySessionFactory()
    audio_path = tmp_path / "kazakh-clarification.ogg"
    audio_path.write_text("stub", encoding="utf-8")

    handled = await try_handle_statement_voice(session_factory, message, audio_path)

    assert handled is True
    assert session_factory.session.commit_calls == 1
    assert "Statement import complete." in str(message.answers[0]["text"])


@pytest.mark.asyncio
async def test_try_handle_statement_voice_routes_latest_status_shortcut(monkeypatch, tmp_path) -> None:
    callback_calls: list[tuple[int, int | None, str, str]] = []

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
            raise AssertionError("process_clarification_text should not run for latest-status shortcut")

    class FakeSpeechAdapter:
        def transcribe(self, audio_path: Path) -> str:
            assert audio_path.name == "latest-status.ogg"
            return "latest status"

    async def fake_build_statement_callback_reply(
        service,
        *,
        telegram_user_id: int,
        telegram_chat_id: int | None = None,
        action: str,
        lang: str = "en",
    ):
        assert isinstance(service, FakeStatementImportService)
        callback_calls.append((telegram_user_id, telegram_chat_id, action, lang))
        return ("Latest statement: voice.csv", None, "Loaded latest statement status", False)

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)
    monkeypatch.setattr(statement_handlers, "SpeechAdapter", FakeSpeechAdapter)
    monkeypatch.setattr(statement_handlers, "build_statement_callback_reply", fake_build_statement_callback_reply)

    message = FakeMessage()
    session_factory = DummySessionFactory()
    audio_path = tmp_path / "latest-status.ogg"
    audio_path.write_text("stub", encoding="utf-8")

    handled = await try_handle_statement_voice(session_factory, message, audio_path)

    assert handled is True
    assert callback_calls == [(42, 99, "latest", "en")]
    assert session_factory.session.commit_calls == 0
    assert message.answers == [{"text": "Latest statement: voice.csv", "reply_markup": None}]


@pytest.mark.asyncio
async def test_try_handle_statement_voice_routes_source_shortcut_from_history_index(monkeypatch, tmp_path) -> None:
    source_calls: list[tuple[int, str]] = []

    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def get_pending_clarification(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return None

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=8,
                source_name="Halyk",
                original_filename="halyk.xlsx",
                parse_status="completed",
                imported_at="2026-08-13 11:30",
                parsed_count=9,
                auto_count=9,
                unclear_count=0,
                remaining_clarifications=0,
            )

        async def get_recent_history(self, telegram_user_id: int, *, limit: int = 5):
            assert telegram_user_id == 42
            assert limit == 5
            return [
                StatementHistorySnapshot(
                    imported_statement_id=8,
                    source_name="Halyk",
                    original_filename="halyk.xlsx",
                    parse_status="completed",
                    imported_at="2026-08-13 11:30",
                    parsed_count=9,
                    auto_count=9,
                    unclear_count=0,
                    remaining_clarifications=0,
                ),
                StatementHistorySnapshot(
                    imported_statement_id=7,
                    source_name="Kaspi",
                    original_filename="kaspi.csv",
                    parse_status="clarification_required",
                    imported_at="2026-08-13 10:00",
                    parsed_count=2,
                    auto_count=0,
                    unclear_count=1,
                    remaining_clarifications=1,
                ),
            ]

        async def process_clarification_text(self, **kwargs):
            raise AssertionError("process_clarification_text should not run for voice source shortcut")

    class FakeSpeechAdapter:
        def transcribe(self, audio_path: Path) -> str:
            assert audio_path.name == "source-history.ogg"
            return "source 2"

    async def fake_send_statement_source_message(
        message,
        service,
        *,
        telegram_user_id: int,
        statement_id: int,
        lang: str = "en",
    ):
        assert isinstance(service, FakeStatementImportService)
        assert telegram_user_id == 42
        assert lang == "en"
        source_calls.append((statement_id, lang))
        message.documents.append({"document": "kaspi.csv", "caption": "Original statement source: kaspi.csv"})
        return ("Sent statement source: kaspi.csv", False)

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)
    monkeypatch.setattr(statement_handlers, "SpeechAdapter", FakeSpeechAdapter)
    monkeypatch.setattr(statement_handlers, "_send_statement_source_message", fake_send_statement_source_message)

    message = FakeMessage()
    session_factory = DummySessionFactory()
    audio_path = tmp_path / "source-history.ogg"
    audio_path.write_text("stub", encoding="utf-8")

    handled = await try_handle_statement_voice(session_factory, message, audio_path)

    assert handled is True
    assert source_calls == [(7, "en")]
    assert session_factory.session.commit_calls == 0
    assert message.answers == []
    assert message.documents == [{"document": "kaspi.csv", "caption": "Original statement source: kaspi.csv"}]


@pytest.mark.asyncio
async def test_try_handle_statement_voice_routes_localized_source_shortcut_from_spoken_history_index(monkeypatch, tmp_path) -> None:
    source_calls: list[tuple[int, str]] = []

    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def get_pending_clarification(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return None

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=8,
                source_name="Halyk",
                original_filename="halyk.xlsx",
                parse_status="completed",
                imported_at="2026-08-13 11:30",
                parsed_count=9,
                auto_count=9,
                unclear_count=0,
                remaining_clarifications=0,
            )

        async def get_recent_history(self, telegram_user_id: int, *, limit: int = 5):
            assert telegram_user_id == 42
            assert limit == 5
            return [
                StatementHistorySnapshot(
                    imported_statement_id=8,
                    source_name="Halyk",
                    original_filename="halyk.xlsx",
                    parse_status="completed",
                    imported_at="2026-08-13 11:30",
                    parsed_count=9,
                    auto_count=9,
                    unclear_count=0,
                    remaining_clarifications=0,
                ),
                StatementHistorySnapshot(
                    imported_statement_id=7,
                    source_name="Kaspi",
                    original_filename="kaspi.csv",
                    parse_status="clarification_required",
                    imported_at="2026-08-13 10:00",
                    parsed_count=2,
                    auto_count=0,
                    unclear_count=1,
                    remaining_clarifications=1,
                ),
            ]

        async def process_clarification_text(self, **kwargs):
            raise AssertionError("process_clarification_text should not run for voice source shortcut")

    class FakeSpeechAdapter:
        def transcribe(self, audio_path: Path) -> str:
            assert audio_path.name == "source-history-localized.ogg"
            return "источник второй"

    async def fake_send_statement_source_message(
        message,
        service,
        *,
        telegram_user_id: int,
        statement_id: int,
        lang: str = "en",
    ):
        assert isinstance(service, FakeStatementImportService)
        assert telegram_user_id == 42
        assert lang == "en"
        source_calls.append((statement_id, lang))
        message.documents.append({"document": "kaspi.csv", "caption": "Original statement source: kaspi.csv"})
        return ("Sent statement source: kaspi.csv", False)

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)
    monkeypatch.setattr(statement_handlers, "SpeechAdapter", FakeSpeechAdapter)
    monkeypatch.setattr(statement_handlers, "_send_statement_source_message", fake_send_statement_source_message)

    message = FakeMessage()
    session_factory = DummySessionFactory()
    audio_path = tmp_path / "source-history-localized.ogg"
    audio_path.write_text("stub", encoding="utf-8")

    handled = await try_handle_statement_voice(session_factory, message, audio_path)

    assert handled is True
    assert source_calls == [(7, "en")]
    assert session_factory.session.commit_calls == 0
    assert message.answers == []
    assert message.documents == [{"document": "kaspi.csv", "caption": "Original statement source: kaspi.csv"}]


@pytest.mark.asyncio
async def test_try_handle_statement_voice_routes_reference_first_latest_source_shortcut(monkeypatch, tmp_path) -> None:
    source_calls: list[tuple[int, str]] = []

    class FakeStatementImportService:
        def __init__(self, session) -> None:
            self.session = session

        async def get_pending_clarification(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return None

        async def get_latest_status(self, telegram_user_id: int):
            assert telegram_user_id == 42
            return StatementStatusSnapshot(
                imported_statement_id=8,
                source_name="Halyk",
                original_filename="halyk.xlsx",
                parse_status="completed",
                imported_at="2026-08-13 11:30",
                parsed_count=9,
                auto_count=9,
                unclear_count=0,
                remaining_clarifications=0,
            )

        async def process_clarification_text(self, **kwargs):
            raise AssertionError("process_clarification_text should not run for voice source shortcut")

    class FakeSpeechAdapter:
        def transcribe(self, audio_path: Path) -> str:
            assert audio_path.name == "latest-source.ogg"
            return "latest source file please"

    async def fake_send_statement_source_message(
        message,
        service,
        *,
        telegram_user_id: int,
        statement_id: int,
        lang: str = "en",
    ):
        assert isinstance(service, FakeStatementImportService)
        assert telegram_user_id == 42
        assert lang == "en"
        source_calls.append((statement_id, lang))
        message.documents.append({"document": "halyk.xlsx", "caption": "Original statement source: halyk.xlsx"})
        return ("Sent statement source: halyk.xlsx", False)

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)
    monkeypatch.setattr(statement_handlers, "SpeechAdapter", FakeSpeechAdapter)
    monkeypatch.setattr(statement_handlers, "_send_statement_source_message", fake_send_statement_source_message)

    message = FakeMessage()
    session_factory = DummySessionFactory()
    audio_path = tmp_path / "latest-source.ogg"
    audio_path.write_text("stub", encoding="utf-8")

    handled = await try_handle_statement_voice(session_factory, message, audio_path)

    assert handled is True
    assert source_calls == [(8, "en")]
    assert session_factory.session.commit_calls == 0
    assert message.answers == []
    assert message.documents == [{"document": "halyk.xlsx", "caption": "Original statement source: halyk.xlsx"}]


@pytest.mark.asyncio
async def test_try_handle_statement_voice_returns_localized_failure_when_clarification_crashes(monkeypatch, tmp_path) -> None:
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
            raise RuntimeError("Classifier unavailable.")

    class FakeSpeechAdapter:
        def transcribe(self, audio_path: Path) -> str:
            assert audio_path.name == "clarification.ogg"
            return "business parts"

    monkeypatch.setattr(statement_handlers, "StatementImportService", FakeStatementImportService)
    monkeypatch.setattr(statement_handlers, "SpeechAdapter", FakeSpeechAdapter)

    message = FakeMessage()
    session_factory = DummySessionFactory()
    audio_path = tmp_path / "clarification.ogg"
    audio_path.write_text("stub", encoding="utf-8")

    handled = await try_handle_statement_voice(session_factory, message, audio_path)

    assert handled is True
    assert session_factory.session.commit_calls == 0
    assert message.answers[0]["text"] == (
        "Could not save this clarification right now. Please try again. Details: Classifier unavailable."
    )
