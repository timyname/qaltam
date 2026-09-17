from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.db.base import Base
from backend.app.models.account import Account
from backend.app.models.enums import AccountType, TransactionType
from backend.app.schemas.ingestion import TransactionDraft
from backend.app.services.transaction_service import TransactionService


@pytest.mark.asyncio
async def test_transaction_service_creates_default_account_and_updates_balance():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        service = TransactionService(session)
        draft = TransactionDraft(
            amount=Decimal("1500"),
            category="taxi",
            transaction_type=TransactionType.EXPENSE,
            note="1500 taxi",
            source_text="1500 taxi",
        )
        transaction = await service.create_from_draft(draft, AccountType.PERSONAL)
        await session.commit()

        result = await session.execute(select(Account))
        account = result.scalars().one()

        assert account.name == "Personal Pocket"
        assert account.balance == Decimal("-1500.00") or account.balance == Decimal("-1500")
        assert transaction.category == "taxi"

    await engine.dispose()
