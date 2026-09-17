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
async def profile_client() -> AsyncGenerator[TestClient, None]:
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
async def test_profile_preferences_route_persists_preferred_language(profile_client: TestClient) -> None:
    response = profile_client.patch(
        "/api/v1/profile/preferences",
        headers=actor_headers(telegram_user_id=9025, role="family_member"),
        json={"telegram_user_id": 9025, "preferred_language": "uk-UA"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "telegram_user_id": 9025,
        "preferred_language": "uk",
    }

    dashboard = profile_client.get(
        "/api/v1/dashboard/micro",
        headers=actor_headers(telegram_user_id=9025, role="family_member"),
    )
    assert dashboard.status_code == 200
    assert dashboard.json()["preferred_language"] == "uk"


@pytest.mark.asyncio
async def test_profile_preferences_route_enforces_actor_identity(profile_client: TestClient) -> None:
    response = profile_client.patch(
        "/api/v1/profile/preferences",
        headers=actor_headers(telegram_user_id=9025),
        json={"telegram_user_id": 9001, "preferred_language": "en"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Telegram actor does not match the requested telegram_user_id."
