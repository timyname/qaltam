from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi.testclient import TestClient
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.db.base import Base
from backend.app.db.database import get_session
from backend.app.main import create_app


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
async def dashboard_client() -> AsyncGenerator[TestClient, None]:
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
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_macro_requires_owner_lane(dashboard_client: TestClient) -> None:
    allowed_response = dashboard_client.get("/api/v1/dashboard/macro", headers=actor_headers(role="cashier"))
    assert allowed_response.status_code == 200

    forbidden_response = dashboard_client.get(
        "/api/v1/dashboard/macro",
        headers=actor_headers(role="family_member"),
    )
    assert forbidden_response.status_code == 403
    assert "owner, cfo, coo, cashier" in forbidden_response.json()["detail"]


@pytest.mark.asyncio
async def test_dashboard_micro_uses_actor_identity(dashboard_client: TestClient) -> None:
    response = dashboard_client.get("/api/v1/dashboard/micro", headers=actor_headers(telegram_user_id=9012))
    assert response.status_code == 200
    assert response.json()["profile_name"] is None

    mismatch = dashboard_client.get(
        "/api/v1/dashboard/micro",
        headers=actor_headers(telegram_user_id=9012),
        params={"telegram_user_id": 9001},
    )
    assert mismatch.status_code == 403
    assert mismatch.json()["detail"] == "Telegram actor does not match the requested telegram_user_id."
