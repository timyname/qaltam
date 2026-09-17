from __future__ import annotations

from collections.abc import AsyncGenerator
from decimal import Decimal

from fastapi.testclient import TestClient
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.core.config import get_settings
from backend.app.db.base import Base
from backend.app.db.database import get_session
from backend.app.main import create_app
from backend.app.models.account import Account
from backend.app.models.profile import UserProfile
from backend.app.models.transaction import Transaction


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
async def quick_add_client() -> AsyncGenerator[tuple[TestClient, async_sessionmaker[AsyncSession]], None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    settings = get_settings()
    original_deepseek_api_key = settings.deepseek_api_key
    settings.deepseek_api_key = ""

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
    settings.deepseek_api_key = original_deepseek_api_key
    await engine.dispose()


@pytest.mark.asyncio
async def test_quick_add_route_accepts_structured_shortcut_payload(quick_add_client) -> None:
    client, session_factory = quick_add_client
    settings = get_settings()

    response = client.post(
        "/api/v1/quick-add",
        headers={"X-API-KEY": settings.quick_add_api_key},
        json={
            "amount": "17000",
            "category": "kassa",
            "account_type": "business",
            "transaction_type": "expense",
            "note": "manual shortcut",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["route"] == "structured"
    assert payload["account_type"] == "business"
    assert payload["transaction"]["category"] == "kassa"
    assert payload["transaction"]["amount"] == "17000"

    async with session_factory() as session:
        transaction = (await session.execute(select(Transaction))).scalars().one()
        account = (await session.execute(select(Account))).scalars().one()
        assert transaction.category == "kassa"
        assert transaction.amount == Decimal("17000")
        assert account.type.value == "business"


@pytest.mark.asyncio
async def test_quick_add_route_accepts_mini_app_text_capture_without_api_key(quick_add_client) -> None:
    client, session_factory = quick_add_client

    response = client.post(
        "/api/v1/quick-add",
        headers=actor_headers(),
        json={
            "raw_text": "+150000 avans",
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "account_type": "business",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["route"] == "text_parser"
    assert payload["account_type"] == "business"
    assert payload["transaction"]["type"] == "income"
    assert payload["transaction"]["category"] == "avans"
    assert payload["message"].startswith("Income saved:")

    async with session_factory() as session:
        profile = (await session.execute(select(UserProfile))).scalars().one()
        transaction = (await session.execute(select(Transaction))).scalars().one()
        assert profile.telegram_user_id == 9001
        assert transaction.amount == Decimal("150000")


@pytest.mark.asyncio
async def test_transactions_alias_and_query_are_isolated_per_user(quick_add_client) -> None:
    client, _ = quick_add_client

    create_first = client.post(
        "/api/v1/transactions",
        headers=actor_headers(telegram_user_id=9001, telegram_chat_id=9001),
        json={
            "raw_text": "17000 бар",
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "account_type": "personal",
        },
    )
    create_second = client.post(
        "/api/v1/transactions",
        headers=actor_headers(telegram_user_id=9002, telegram_chat_id=9002),
        json={
            "raw_text": "9000 бар",
            "telegram_user_id": 9002,
            "telegram_chat_id": 9002,
            "account_type": "personal",
        },
    )

    assert create_first.status_code == 200
    assert create_second.status_code == 200

    response = client.post(
        "/api/v1/transactions/query",
        headers=actor_headers(telegram_user_id=9001, telegram_chat_id=9001),
        json={
            "question": "Сколько ушло на бар?",
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_amount"] == "17000.00"
    assert payload["transaction_count"] == 1
    assert payload["route"] in {"heuristic_intent", "deepseek_intent"}


def test_quick_add_route_rejects_contextless_requests_without_api_key(quick_add_client) -> None:
    client, _ = quick_add_client

    response = client.post(
        "/api/v1/quick-add",
        json={
            "raw_text": "17000 kassa",
        },
    )

    assert response.status_code == 401
    assert "telegram_user_id" in response.json()["detail"]


def test_quick_add_route_rejects_actor_mismatch_without_api_key(quick_add_client) -> None:
    client, _ = quick_add_client

    response = client.post(
        "/api/v1/quick-add",
        headers=actor_headers(telegram_user_id=9002, telegram_chat_id=9002),
        json={
            "raw_text": "17000 kassa",
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "account_type": "business",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Telegram actor does not match the requested telegram_user_id."
