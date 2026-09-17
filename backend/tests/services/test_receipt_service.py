from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.db.base import Base
from backend.app.services.receipt_service import ReceiptService


@pytest.mark.asyncio
async def test_receipt_service_parses_persists_and_tracks_inflation():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        service = ReceiptService(session)
        first = service.analyze_text(
            "\n".join(
                [
                    "MAGNUM EXPRESS",
                    "BANAN 2 x 450 900",
                    "MILK 1 x 620 620",
                    "ИТОГО 1520",
                ]
            )
        )
        assert first is not None
        first.purchased_at = first.purchased_at - timedelta(days=10)
        await service.persist_receipt(telegram_user_id=77, receipt=first)

        second = service.analyze_text(
            "\n".join(
                [
                    "MAGNUM EXPRESS",
                    "BANAN 2 x 510 1020",
                    "MILK 1 x 650 650",
                    "TOTAL 1670",
                ]
            )
        )
        assert second is not None
        await service.persist_receipt(telegram_user_id=77, receipt=second)
        await session.commit()

        insights = await service.get_insights(days=30)

        assert insights.recent_receipts_total == 2
        assert insights.recent_receipts_amount == Decimal("3190")
        assert insights.tracked_skus_total >= 2
        assert insights.last_receipt is not None
        assert insights.last_receipt.merchant_name == "MAGNUM EXPRESS"
        assert any(item.sku_key == "banan" and item.price_change_pct == Decimal("13.33") for item in insights.inflation_leaders)

    await engine.dispose()
