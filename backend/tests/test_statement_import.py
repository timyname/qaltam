from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.db.base import Base
from backend.app.models.profile import ImportedStatement, MemoryNote
from backend.app.models.transaction import Transaction
from backend.app.services.deepseek_client import DeepSeekResponse
from backend.app.services.statement_classifier import StatementClassifier
from backend.app.services.statement_import_service import (
    ActiveStatementImportConflictError,
    StatementImportService,
)
from backend.app.services.statement_parser import StatementParser


class FakeDeepSeekClient:
    api_key = "test-key"

    async def extract_json(self, system_prompt: str, user_prompt: str) -> DeepSeekResponse:
        if "Convert the user's clarification" in system_prompt:
            payload = {
                "account_type": "business",
                "life_sector": "inventory_parts",
                "explanation": "Arman T. is the spare-parts supplier.",
            }
            return DeepSeekResponse(raw_text=json.dumps(payload), json_data=payload)

        payload = {
            "auto_categorized": [
                {
                    "index": 0,
                    "account_type": "business",
                    "life_sector": "sales_income",
                    "confidence": 0.96,
                    "rationale": "Incoming client payment.",
                }
            ],
            "unclear_items": [
                {
                    "index": 1,
                    "reason": "Ambiguous P2P transfer to a person.",
                    "suggested_account_type": "business",
                    "suggested_life_sector": "inventory_parts",
                }
            ],
        }
        return DeepSeekResponse(raw_text=json.dumps(payload), json_data=payload)


class NoManualClarificationDeepSeekClient(FakeDeepSeekClient):
    async def extract_json(self, system_prompt: str, user_prompt: str) -> DeepSeekResponse:
        if "Convert the user's clarification" in system_prompt:
            raise AssertionError("manual clarification extraction should not run for numeric quick choices")
        return await super().extract_json(system_prompt, user_prompt)


class LearnedRuleQuickChoiceDeepSeekClient(FakeDeepSeekClient):
    async def extract_json(self, system_prompt: str, user_prompt: str) -> DeepSeekResponse:
        if "Convert the user's clarification" in system_prompt:
            raise AssertionError("manual clarification extraction should not run for learned-rule quick choices")

        payload = {
            "auto_categorized": [],
            "unclear_items": [
                {
                    "index": 0,
                    "reason": "Ambiguous P2P transfer to a person.",
                }
            ],
        }
        return DeepSeekResponse(raw_text=json.dumps(payload), json_data=payload)


class LearnedRulePreferredOverSuggestionDeepSeekClient(FakeDeepSeekClient):
    async def extract_json(self, system_prompt: str, user_prompt: str) -> DeepSeekResponse:
        if "Convert the user's clarification" in system_prompt:
            raise AssertionError("manual clarification extraction should not run for learned-first numeric quick choices")

        payload = {
            "auto_categorized": [],
            "unclear_items": [
                {
                    "index": 0,
                    "reason": "Ambiguous P2P transfer to a person.",
                    "suggested_account_type": "business",
                    "suggested_life_sector": "sales_income",
                }
            ],
        }
        return DeepSeekResponse(raw_text=json.dumps(payload), json_data=payload)


@pytest.mark.asyncio
async def test_statement_import_parses_classifies_and_persists_memory_rule(tmp_path: Path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    statement_path = tmp_path / "kaspi_statement.csv"
    statement_path.write_text(
        "\n".join(
            [
                "date,amount,counterparty,description",
                "2026-08-10,150000,Client LLP,Kaspi incoming client payment",
                "2026-08-11,-45000,Arman T.,Kaspi transfer to supplier",
            ]
        ),
        encoding="utf-8",
    )

    async with session_factory() as session:
        classifier = StatementClassifier(session, client=FakeDeepSeekClient())
        service = StatementImportService(session, classifier=classifier)
        result = await service.import_file(
            telegram_user_id=77,
            telegram_chat_id=88,
            file_path=statement_path,
            original_filename=statement_path.name,
        )
        await session.commit()

        assert result.parsed_count == 2
        assert result.auto_count == 1
        assert result.unclear_count == 1
        assert "Processing bank statement (2 items)" in result.summary_message
        assert result.prompt_message is not None
        assert "Clarification 1 of 1" in result.prompt_message
        assert "Arman T." in result.prompt_message
        assert "Statement note: Kaspi transfer to supplier" in result.prompt_message
        assert "Suggested quick choice: Business / Inventory / Parts" in result.prompt_message
        assert "Fastest confirm now: `1` = Suggested: Business / Inventory / Parts" in result.prompt_message
        assert "Quick choices:" in result.prompt_message
        assert "1. Suggested: Business / Inventory / Parts" in result.prompt_message
        pending = await service.get_pending_clarification(77)
        assert pending is not None
        assert pending["items"][0]["matched_rules"] == []

        statement = (
            await session.execute(select(ImportedStatement).where(ImportedStatement.original_filename == "kaspi_statement.csv"))
        ).scalars().one()
        assert statement.parse_status == "clarification_required"
        assert statement.raw_content is not None
        assert "Client LLP" in statement.raw_content

        transaction_count = await session.scalar(select(func.count()).select_from(Transaction))
        assert transaction_count == 1

        clarification_reply = await service.process_clarification_text(
            telegram_user_id=77,
            telegram_chat_id=88,
            answer_text="business parts from Arman",
        )
        await session.commit()

        assert clarification_reply == "Statement import complete. All unclear items were resolved and saved into memory."

        transaction_count = await session.scalar(select(func.count()).select_from(Transaction))
        assert transaction_count == 2

        categories = list((await session.execute(select(Transaction.category).order_by(Transaction.id.asc()))).scalars().all())
        assert categories == ["sales_income", "inventory_parts"]

        rule_note = (
            await session.execute(select(MemoryNote).where(MemoryNote.kind == "clarification_rule"))
        ).scalars().one()
        assert "inventory_parts" in rule_note.content

        repeat_path = tmp_path / "halyk_repeat.csv"
        repeat_path.write_text(
            "\n".join(
                [
                    "date,amount,counterparty,description",
                    "2026-08-12,-30000,Arman T.,Repeat supplier transfer",
                ]
            ),
            encoding="utf-8",
        )
        repeat_result = await service.import_file(
            telegram_user_id=77,
            telegram_chat_id=88,
            file_path=repeat_path,
            original_filename=repeat_path.name,
        )
        await session.commit()

        assert repeat_result.auto_count == 1
        assert repeat_result.unclear_count == 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_statement_import_resolves_numeric_quick_choice_without_manual_llm(tmp_path: Path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    statement_path = tmp_path / "numeric_quick_choice.csv"
    statement_path.write_text(
        "\n".join(
            [
                "date,amount,counterparty,description",
                "2026-08-10,150000,Client LLP,Kaspi incoming client payment",
                "2026-08-11,-45000,Arman T.,Kaspi transfer to supplier",
            ]
        ),
        encoding="utf-8",
    )

    async with session_factory() as session:
        classifier = StatementClassifier(session, client=NoManualClarificationDeepSeekClient())
        service = StatementImportService(session, classifier=classifier)

        result = await service.import_file(
            telegram_user_id=77,
            telegram_chat_id=88,
            file_path=statement_path,
            original_filename=statement_path.name,
        )
        await session.commit()

        assert result.prompt_message is not None
        assert "1. Suggested: Business / Inventory / Parts" in result.prompt_message

        clarification_reply = await service.process_clarification_text(
            telegram_user_id=77,
            telegram_chat_id=88,
            answer_text="1",
        )
        await session.commit()

        assert clarification_reply == "Statement import complete. All unclear items were resolved and saved into memory."

        categories = list((await session.execute(select(Transaction.category).order_by(Transaction.id.asc()))).scalars().all())
        assert categories == ["sales_income", "inventory_parts"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_statement_import_surfaces_learned_rule_quick_choice_without_manual_llm(tmp_path: Path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    statement_path = tmp_path / "learned_rule_choice.csv"
    statement_path.write_text(
        "\n".join(
            [
                "date,amount,counterparty,description",
                "2026-08-11,-45000,Kaspi P2P,Transfer to Arman T. for supplier",
            ]
        ),
        encoding="utf-8",
    )

    async with session_factory() as session:
        classifier = StatementClassifier(session, client=LearnedRuleQuickChoiceDeepSeekClient())
        service = StatementImportService(session, classifier=classifier)
        await service.memory.save_clarification_rule(
            77,
            match_key="arman t",
            account_type="business",
            life_sector="inventory_parts",
            explanation="Arman T. is usually a supplier payment.",
        )

        result = await service.import_file(
            telegram_user_id=77,
            telegram_chat_id=88,
            file_path=statement_path,
            original_filename=statement_path.name,
        )
        await session.commit()

        assert result.prompt_message is not None
        assert "Learned precedents:" in result.prompt_message
        assert "- Business / Inventory / Parts: Arman T. is usually a supplier payment." in result.prompt_message
        assert "Fastest confirm now: `1` = Learned: Business / Inventory / Parts" in result.prompt_message
        assert "Shortcut: reply `same as before` to reuse the learned precedent." in result.prompt_message
        assert "1. Learned: Business / Inventory / Parts" in result.prompt_message

        pending = await service.get_pending_clarification(77)
        assert pending is not None
        assert pending["items"][0]["matched_rules"] == [
            {
                "match_key": "arman t",
                "account_type": "business",
                "life_sector": "inventory_parts",
                "explanation": "Arman T. is usually a supplier payment.",
            }
        ]

        clarification_reply = await service.process_clarification_text(
            telegram_user_id=77,
            telegram_chat_id=88,
            answer_text="1",
        )
        await session.commit()

        assert clarification_reply == "Statement import complete. All unclear items were resolved and saved into memory."

        categories = list((await session.execute(select(Transaction.category).order_by(Transaction.id.asc()))).scalars().all())
        assert categories == ["inventory_parts"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_statement_import_prioritizes_learned_rule_before_suggestion_for_numeric_shortcuts(tmp_path: Path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    statement_path = tmp_path / "learned_before_suggested.csv"
    statement_path.write_text(
        "\n".join(
            [
                "date,amount,counterparty,description",
                "2026-08-11,-45000,Kaspi P2P,Transfer to Arman T. from client settlement",
            ]
        ),
        encoding="utf-8",
    )

    async with session_factory() as session:
        classifier = StatementClassifier(session, client=LearnedRulePreferredOverSuggestionDeepSeekClient())
        service = StatementImportService(session, classifier=classifier)
        await service.memory.save_clarification_rule(
            77,
            match_key="arman t",
            account_type="business",
            life_sector="inventory_parts",
            explanation="Arman T. is usually a supplier payment.",
        )

        result = await service.import_file(
            telegram_user_id=77,
            telegram_chat_id=88,
            file_path=statement_path,
            original_filename=statement_path.name,
        )
        await session.commit()

        assert result.prompt_message is not None
        assert "Suggested quick choice: Business / Sales / Income" in result.prompt_message
        assert "Fastest confirm now: `1` = Learned: Business / Inventory / Parts" in result.prompt_message
        assert "1. Learned: Business / Inventory / Parts" in result.prompt_message
        assert "2. Suggested: Business / Sales / Income" in result.prompt_message

        clarification_reply = await service.process_clarification_text(
            telegram_user_id=77,
            telegram_chat_id=88,
            answer_text="1",
        )
        await session.commit()

        assert clarification_reply == "Statement import complete. All unclear items were resolved and saved into memory."

        categories = list((await session.execute(select(Transaction.category).order_by(Transaction.id.asc()))).scalars().all())
        assert categories == ["inventory_parts"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_statement_import_reuses_learned_rule_for_same_as_before_without_manual_llm(tmp_path: Path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    statement_path = tmp_path / "same_as_before.csv"
    statement_path.write_text(
        "\n".join(
            [
                "date,amount,counterparty,description",
                "2026-08-11,-45000,Kaspi P2P,Transfer to Arman T. for supplier",
            ]
        ),
        encoding="utf-8",
    )

    async with session_factory() as session:
        classifier = StatementClassifier(session, client=LearnedRuleQuickChoiceDeepSeekClient())
        service = StatementImportService(session, classifier=classifier)
        await service.memory.save_clarification_rule(
            77,
            match_key="arman t",
            account_type="business",
            life_sector="inventory_parts",
            explanation="Arman T. is usually a supplier payment.",
        )

        result = await service.import_file(
            telegram_user_id=77,
            telegram_chat_id=88,
            file_path=statement_path,
            original_filename=statement_path.name,
        )
        await session.commit()

        assert result.prompt_message is not None

        clarification_reply = await service.process_clarification_text(
            telegram_user_id=77,
            telegram_chat_id=88,
            answer_text="same as before",
        )
        await session.commit()

        assert clarification_reply == "Statement import complete. All unclear items were resolved and saved into memory."

        categories = list((await session.execute(select(Transaction.category).order_by(Transaction.id.asc()))).scalars().all())
        assert categories == ["inventory_parts"]

    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("answer_text", "language", "expected_reply"),
    [
        (
            "товар для бизнеса",
            "ru",
            "Импорт выписки завершен. Все неясные операции уточнены и сохранены в память.",
        ),
        (
            "жабдық бизнеске",
            "kk",
            "Үзіндіні импорттау аяқталды. Барлық түсініксіз операциялар нақтыланып, жадқа сақталды.",
        ),
    ],
)
async def test_statement_import_resolves_multilingual_inventory_reply_without_manual_llm(
    tmp_path: Path,
    answer_text: str,
    language: str,
    expected_reply: str,
):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    statement_path = tmp_path / f"multilingual_inventory_{language}.csv"
    statement_path.write_text(
        "\n".join(
            [
                "date,amount,counterparty,description",
                "2026-08-10,150000,Client LLP,Kaspi incoming client payment",
                "2026-08-11,-45000,Arman T.,Kaspi transfer to supplier",
            ]
        ),
        encoding="utf-8",
    )

    async with session_factory() as session:
        classifier = StatementClassifier(session, client=NoManualClarificationDeepSeekClient())
        service = StatementImportService(session, classifier=classifier)

        result = await service.import_file(
            telegram_user_id=77,
            telegram_chat_id=88,
            file_path=statement_path,
            original_filename=statement_path.name,
            language=language,
        )
        await session.commit()

        assert result.prompt_message is not None

        clarification_reply = await service.process_clarification_text(
            telegram_user_id=77,
            telegram_chat_id=88,
            answer_text=answer_text,
            language=language,
        )
        await session.commit()

        assert clarification_reply == expected_reply

        categories = list((await session.execute(select(Transaction.category).order_by(Transaction.id.asc()))).scalars().all())
        assert categories == ["sales_income", "inventory_parts"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_statement_import_resolves_numeric_reply_with_extra_context_without_manual_llm(tmp_path: Path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    statement_path = tmp_path / "numeric_with_context.csv"
    statement_path.write_text(
        "\n".join(
            [
                "date,amount,counterparty,description",
                "2026-08-10,150000,Client LLP,Kaspi incoming client payment",
                "2026-08-11,-45000,Arman T.,Kaspi transfer to supplier",
            ]
        ),
        encoding="utf-8",
    )

    async with session_factory() as session:
        classifier = StatementClassifier(session, client=NoManualClarificationDeepSeekClient())
        service = StatementImportService(session, classifier=classifier)

        result = await service.import_file(
            telegram_user_id=77,
            telegram_chat_id=88,
            file_path=statement_path,
            original_filename=statement_path.name,
        )
        await session.commit()

        assert result.prompt_message is not None

        clarification_reply = await service.process_clarification_text(
            telegram_user_id=77,
            telegram_chat_id=88,
            answer_text="1 business",
        )
        await session.commit()

        assert clarification_reply == "Statement import complete. All unclear items were resolved and saved into memory."

        categories = list((await session.execute(select(Transaction.category).order_by(Transaction.id.asc()))).scalars().all())
        assert categories == ["sales_income", "inventory_parts"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_statement_import_resolves_supplier_payment_phrase_without_manual_llm(tmp_path: Path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    statement_path = tmp_path / "supplier_payment.csv"
    statement_path.write_text(
        "\n".join(
            [
                "date,amount,counterparty,description",
                "2026-08-10,150000,Client LLP,Kaspi incoming client payment",
                "2026-08-11,-45000,Arman T.,Kaspi transfer to supplier",
            ]
        ),
        encoding="utf-8",
    )

    async with session_factory() as session:
        classifier = StatementClassifier(session, client=NoManualClarificationDeepSeekClient())
        service = StatementImportService(session, classifier=classifier)

        result = await service.import_file(
            telegram_user_id=77,
            telegram_chat_id=88,
            file_path=statement_path,
            original_filename=statement_path.name,
        )
        await session.commit()

        assert result.prompt_message is not None

        clarification_reply = await service.process_clarification_text(
            telegram_user_id=77,
            telegram_chat_id=88,
            answer_text="supplier payment",
        )
        await session.commit()

        assert clarification_reply == "Statement import complete. All unclear items were resolved and saved into memory."

        categories = list((await session.execute(select(Transaction.category).order_by(Transaction.id.asc()))).scalars().all())
        assert categories == ["sales_income", "inventory_parts"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_statement_import_localizes_prompt_and_completion_copy(tmp_path: Path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    statement_path = tmp_path / "kaspi_statement_ru.csv"
    statement_path.write_text(
        "\n".join(
            [
                "date,amount,counterparty,description",
                "2026-08-10,150000,Client LLP,Kaspi incoming client payment",
                "2026-08-11,-45000,Arman T.,Kaspi transfer to supplier",
            ]
        ),
        encoding="utf-8",
    )

    async with session_factory() as session:
        classifier = StatementClassifier(session, client=FakeDeepSeekClient())
        service = StatementImportService(session, classifier=classifier)

        result = await service.import_file(
            telegram_user_id=77,
            telegram_chat_id=88,
            file_path=statement_path,
            original_filename=statement_path.name,
            language="ru",
        )
        await session.commit()

        assert result.prompt_message is not None
        assert "Уточнение 1 из 1" in result.prompt_message
        assert "Подсказка" in result.prompt_message

        clarification_reply = await service.process_clarification_text(
            telegram_user_id=77,
            telegram_chat_id=88,
            answer_text="business parts from Arman",
            language="ru",
        )
        await session.commit()

        assert clarification_reply == "Импорт выписки завершен. Все неясные операции уточнены и сохранены в память."

    await engine.dispose()


@pytest.mark.asyncio
async def test_statement_import_blocks_new_import_while_clarification_queue_is_active(tmp_path: Path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    first_statement_path = tmp_path / "first_statement.csv"
    first_statement_path.write_text(
        "\n".join(
            [
                "date,amount,counterparty,description",
                "2026-08-10,150000,Client LLP,Kaspi incoming client payment",
                "2026-08-11,-45000,Arman T.,Kaspi transfer to supplier",
            ]
        ),
        encoding="utf-8",
    )

    second_statement_path = tmp_path / "second_statement.csv"
    second_statement_path.write_text(
        "\n".join(
            [
                "date,amount,counterparty,description",
                "2026-08-12,-30000,Magnum,Card purchase",
            ]
        ),
        encoding="utf-8",
    )

    async with session_factory() as session:
        classifier = StatementClassifier(session, client=FakeDeepSeekClient())
        service = StatementImportService(session, classifier=classifier)

        first_result = await service.import_file(
            telegram_user_id=77,
            telegram_chat_id=88,
            file_path=first_statement_path,
            original_filename=first_statement_path.name,
        )

        assert first_result.unclear_count == 1

        with pytest.raises(ActiveStatementImportConflictError) as exc_info:
            await service.import_file(
                telegram_user_id=77,
                telegram_chat_id=88,
                file_path=second_statement_path,
                original_filename=second_statement_path.name,
            )

        assert (
            str(exc_info.value)
            == 'Finish the active clarification for "first_statement.csv" before importing a new statement. '
            "Remaining clarifications: 1."
        )

    await engine.dispose()


def test_statement_parser_recognizes_single_statement_row_text() -> None:
    assert StatementParser.looks_like_statement_text("2026-08-10 Client LLP +150000")
    assert not StatementParser.looks_like_statement_text("2026-08-10 team sync tomorrow")


@pytest.mark.asyncio
async def test_statement_import_text_accepts_single_statement_row() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        classifier = StatementClassifier(session, client=FakeDeepSeekClient())
        service = StatementImportService(session, classifier=classifier)

        result = await service.import_text(
            telegram_user_id=77,
            telegram_chat_id=88,
            raw_text="2026-08-10 Client LLP +150000",
        )
        await session.commit()

        assert result is not None
        assert result.parsed_count == 1
        assert result.auto_count == 1
        assert result.unclear_count == 0
        assert "Processing bank statement (1 items)" in result.summary_message

        transaction_count = await session.scalar(select(func.count()).select_from(Transaction))
        assert transaction_count == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_statement_import_parses_semicolon_cp1251_csv_with_cyrillic_headers(tmp_path: Path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    statement_path = tmp_path / "halyk_semicolon.csv"
    statement_text = "\n".join(
        [
            "\u0414\u0430\u0442\u0430;\u0421\u0443\u043c\u043c\u0430;\u041a\u043e\u043d\u0442\u0440\u0430\u0433\u0435\u043d\u0442;\u041d\u0430\u0437\u043d\u0430\u0447\u0435\u043d\u0438\u0435 \u043f\u043b\u0430\u0442\u0435\u0436\u0430",
            "10.08.2026;150000,00;\u041a\u043b\u0438\u0435\u043d\u0442 \u0422\u041e\u041e;\u041f\u043e\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u0435 \u043e\u0442 \u043a\u043b\u0438\u0435\u043d\u0442\u0430",
            "11.08.2026;-45000,50;\u0410\u0440\u043c\u0430\u043d \u0422.;\u041f\u0435\u0440\u0435\u0432\u043e\u0434 \u043f\u043e\u0441\u0442\u0430\u0432\u0449\u0438\u043a\u0443",
        ]
    )
    statement_path.write_bytes(statement_text.encode("cp1251"))

    async with session_factory() as session:
        classifier = StatementClassifier(session, client=FakeDeepSeekClient())
        service = StatementImportService(session, classifier=classifier)

        result = await service.import_file(
            telegram_user_id=77,
            telegram_chat_id=88,
            file_path=statement_path,
            original_filename=statement_path.name,
        )
        await session.commit()

        assert result.parsed_count == 2
        assert result.auto_count == 1
        assert result.unclear_count == 1
        assert result.prompt_message is not None
        assert "\u0410\u0440\u043c\u0430\u043d \u0422." in result.prompt_message

        statement = (
            await session.execute(select(ImportedStatement).where(ImportedStatement.original_filename == "halyk_semicolon.csv"))
        ).scalars().one()
        assert statement.raw_content is not None
        assert "\u041a\u043b\u0438\u0435\u043d\u0442 \u0422\u041e\u041e" in statement.raw_content

        clarification_reply = await service.process_clarification_text(
            telegram_user_id=77,
            telegram_chat_id=88,
            answer_text="business supplier payment",
        )
        await session.commit()

        assert clarification_reply == "Statement import complete. All unclear items were resolved and saved into memory."

        amounts = list((await session.execute(select(Transaction.amount).order_by(Transaction.id.asc()))).scalars().all())
        assert amounts == [Decimal("150000.00"), Decimal("45000.50")]

    await engine.dispose()
