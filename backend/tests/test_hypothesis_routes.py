from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.db.base import Base
from backend.app.db.database import get_session
from backend.app.main import create_app
from backend.app.models.account import Account
from backend.app.models.enums import AccountType, ObligationPriority, RoleTag, TransactionType
from backend.app.models.obligation import Obligation
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
async def hypothesis_client() -> AsyncGenerator[TestClient, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        business = Account(name="Main business", type=AccountType.BUSINESS, balance="900000")
        personal = Account(name="Personal pocket", type=AccountType.PERSONAL, balance="120000")
        session.add_all([business, personal])
        await session.flush()
        session.add(
            Transaction(
                account_id=business.id,
                amount="180000",
                category="sales_income",
                type=TransactionType.INCOME,
                role_tag=RoleTag.CFO,
                note="recent sales batch",
                created_at=datetime.combine(date.today() - timedelta(days=3), datetime.min.time()),
            )
        )
        session.add(
            Obligation(
                title="Supplier batch",
                amount="220000",
                due_date=date.today() + timedelta(days=8),
                priority=ObligationPriority.CRITICAL,
                target_type=AccountType.BUSINESS,
            )
        )
        await session.commit()

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
async def test_hypothesis_preview_route_returns_scorecard(hypothesis_client: TestClient) -> None:
    response = hypothesis_client.post(
        "/api/v1/hypotheses/score-preview",
        headers=actor_headers(role="cfo"),
        json={
            "title": "Weekend market push",
            "role_perspective": "COO",
            "required_investment": "180000",
            "time_lag_days": 18,
            "expected_roi": "0.35",
            "risk_level": "medium",
            "status": "draft",
            "days": 45,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Weekend market push"
    assert payload["scorecard"]["verdict"] in {"approve", "stage"}
    assert float(payload["scorecard"]["probability_of_success"]) > 50
    assert payload["agents"][0]["agent"] == "CFO"
    assert len(payload["simulation"]["baseline_curve"]) == 45


def test_hypothesis_preview_route_rejects_family_member_role(hypothesis_client: TestClient) -> None:
    response = hypothesis_client.post(
        "/api/v1/hypotheses/score-preview",
        headers=actor_headers(role="family_member"),
        json={
            "title": "Weekend market push",
            "role_perspective": "COO",
            "required_investment": "180000",
            "time_lag_days": 18,
            "expected_roi": "0.35",
            "risk_level": "medium",
            "status": "draft",
            "days": 45,
        },
    )

    assert response.status_code == 403
    assert "owner, cfo, coo" in response.json()["detail"]
