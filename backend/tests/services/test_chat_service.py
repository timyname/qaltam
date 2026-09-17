from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.db.base import Base
from backend.app.models.enums import ClientMode, RiskLevel, TransactionType
from backend.app.models.receipt import Receipt
from backend.app.models.profile import UserProfile
from backend.app.models.transaction import Transaction
from backend.app.schemas.ingestion import TransactionDraft
from backend.app.services.chat_service import ChatService
from backend.app.services.receipt_service import ParsedReceipt, ParsedReceiptItem


class FakeClassifier:
    async def classify_text(self, text: str) -> TransactionDraft | None:
        return TransactionDraft(
            amount=Decimal("250000"),
            category="rent",
            transaction_type=TransactionType.EXPENSE,
            note=text,
            source_text=text,
            confidence=0.95,
        )


class FakeReceiptService:
    def __init__(self) -> None:
        self.calls: list[tuple[int, Path]] = []

    async def ingest_photo(self, *, telegram_user_id: int, image_path: Path) -> ParsedReceipt | None:
        self.calls.append((telegram_user_id, image_path))
        return ParsedReceipt(
            merchant_name="Magnum",
            total_amount=Decimal("1570"),
            currency="KZT",
            purchased_at=datetime.now(UTC).replace(tzinfo=None),
            raw_text="MAGNUM\nMILK 1 x 650 650\nBANAN 2 x 460 920\nTOTAL 1570",
            items=[
                ParsedReceiptItem(
                    sku_name="MILK",
                    sku_key="milk",
                    category="dairy",
                    quantity=Decimal("1"),
                    unit_price=Decimal("650"),
                    total_price=Decimal("650"),
                ),
                ParsedReceiptItem(
                    sku_name="BANAN",
                    sku_key="banan",
                    category="produce",
                    quantity=Decimal("2"),
                    unit_price=Decimal("460"),
                    total_price=Decimal("920"),
                ),
            ],
        )

    def dominant_category(self, receipt: ParsedReceipt) -> str:
        return "produce"


@pytest.mark.asyncio
async def test_chat_service_uses_llm_classifier_for_freeform_text():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        profile = UserProfile(
            telegram_user_id=101,
            telegram_chat_id=202,
            display_name="Ali",
            client_mode=ClientMode.MIXED,
            risk_level=RiskLevel.MEDIUM,
            preferred_language="ru",
            communication_style="short",
            owner_priority="cash",
            privacy_policy_note="local only",
            onboarding_step="completed",
            onboarding_completed=True,
        )
        session.add(profile)
        await session.flush()

        service = ChatService(session, classifier=FakeClassifier())
        reply = await service.process_text(
            telegram_user_id=101,
            telegram_chat_id=202,
            text="Оплатил аренду офиса двести пятьдесят тысяч тенге",
        )

        result = await session.execute(select(Transaction))
        transaction = result.scalars().one()

        assert "250000" in reply
        assert transaction.category == "rent"
        assert transaction.amount == Decimal("250000")

    await engine.dispose()


@pytest.mark.asyncio
async def test_chat_service_honors_english_profile_preference_for_text_replies():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        profile = UserProfile(
            telegram_user_id=303,
            telegram_chat_id=404,
            display_name="Amina",
            client_mode=ClientMode.MIXED,
            risk_level=RiskLevel.MEDIUM,
            preferred_language="en",
            communication_style="short",
            owner_priority="cash",
            privacy_policy_note="local only",
            onboarding_step="completed",
            onboarding_completed=True,
        )
        session.add(profile)
        await session.flush()

        service = ChatService(session, classifier=FakeClassifier())
        reply = await service.process_text(
            telegram_user_id=303,
            telegram_chat_id=404,
            text="Office rent 250000 tenge",
        )

        assert reply.startswith("Logged:")
        assert "250000" in reply

    await engine.dispose()


@pytest.mark.asyncio
async def test_chat_service_persists_receipt_transaction_from_photo():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        profile = UserProfile(
            telegram_user_id=101,
            telegram_chat_id=202,
            display_name="Ali",
            client_mode=ClientMode.MIXED,
            risk_level=RiskLevel.MEDIUM,
            preferred_language="ru",
            communication_style="short",
            owner_priority="cash",
            privacy_policy_note="local only",
            onboarding_step="completed",
            onboarding_completed=True,
        )
        session.add(profile)
        await session.flush()

        service = ChatService(session, receipt_service=FakeReceiptService())
        reply = await service.process_photo(
            telegram_user_id=101,
            telegram_chat_id=202,
            image_path=Path("C:/tmp/demo-receipt.jpg"),
        )

        receipt_count = len((await session.execute(select(Receipt))).scalars().all())
        transaction = (await session.execute(select(Transaction))).scalars().one()

        assert receipt_count == 0
        assert "Magnum" in reply
        assert "1570" in reply
        assert transaction.category == "produce"
        assert transaction.amount == Decimal("1570")

    await engine.dispose()


@pytest.mark.asyncio
async def test_chat_service_seeds_profile_language_from_telegram_code():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        service = ChatService(session)
        profile = await service.get_or_create_profile(
            telegram_user_id=505,
            telegram_chat_id=606,
            fallback_language_code="uk-UA",
        )

        assert profile.preferred_language == "uk"

    await engine.dispose()
