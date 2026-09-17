from __future__ import annotations

from collections.abc import AsyncGenerator
from decimal import Decimal

from fastapi.testclient import TestClient
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.db.base import Base
from backend.app.db.database import get_session
from backend.app.main import create_app
from backend.app.models.receipt import Receipt
from backend.app.models.transaction import Transaction
from backend.app.services.ocr_adapter import OcrAdapter


def actor_headers(
    telegram_user_id: int = 9001,
    telegram_chat_id: int = 9001,
    role: str = "owner",
) -> dict[str, str]:
    return {
        "X-Telegram-User-Id": str(telegram_user_id),
        "X-Telegram-Chat-Id": str(telegram_chat_id),
        "X-Qaltam-Role": role,
    }


@pytest_asyncio.fixture
async def receipt_client() -> AsyncGenerator[tuple[TestClient, async_sessionmaker[AsyncSession]], None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as client:
        yield client, session_factory

    app.dependency_overrides.clear()
    await engine.dispose()


def test_receipt_upload_route_persists_receipt_and_transaction(receipt_client, monkeypatch) -> None:
    client, session_factory = receipt_client

    def fake_extract_text(self, _image_path):
        return "\n".join(
            [
                "MAGNUM EXPRESS",
                "BANAN 2 x 510 1020",
                "MILK 1 x 650 650",
                "TOTAL 1670",
            ]
        )

    monkeypatch.setattr(OcrAdapter, "extract_text", fake_extract_text)

    response = client.post(
        "/api/v1/receipts/upload",
        headers=actor_headers(),
        data={"telegram_user_id": "9001", "telegram_chat_id": "9001"},
        files={"file": ("receipt.jpg", b"fake-image", "image/jpeg")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "MAGNUM EXPRESS" in payload["message"]
    assert payload["receipt"]["merchant_name"] == "MAGNUM EXPRESS"
    assert Decimal(payload["receipt"]["total_amount"]) == Decimal("1670")

    import asyncio

    async def assert_records() -> None:
        async with session_factory() as session:
            receipt = (await session.execute(select(Receipt))).scalars().one()
            transaction = (await session.execute(select(Transaction))).scalars().one()
            assert receipt.total_amount == Decimal("1670")
            assert transaction.amount == Decimal("1670")
            assert transaction.type.value == "expense"

    asyncio.run(assert_records())


def test_receipt_upload_route_rejects_actor_mismatch(receipt_client, monkeypatch) -> None:
    client, _ = receipt_client

    monkeypatch.setattr(OcrAdapter, "extract_text", lambda *_args, **_kwargs: "TOTAL 900")

    response = client.post(
        "/api/v1/receipts/upload",
        headers=actor_headers(telegram_user_id=9002, telegram_chat_id=9002),
        data={"telegram_user_id": "9001", "telegram_chat_id": "9001"},
        files={"file": ("receipt.jpg", b"fake-image", "image/jpeg")},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Telegram actor does not match the requested telegram_user_id."
