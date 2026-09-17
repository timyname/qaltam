from datetime import date, timedelta
from decimal import Decimal

from backend.app.models.enums import RiskLevel, RoleTag
from backend.app.schemas.hypothesis import HypothesisScoreRequest
from backend.app.services.scoring_engine import ScoringEngine


TODAY = date(2026, 8, 13)


def test_scoring_engine_approves_healthy_experiment() -> None:
    result = ScoringEngine.evaluate(
        today=TODAY,
        business_balance=Decimal("1000000"),
        reserve_buffer=Decimal("150000"),
        obligations=[
            {
                "title": "Rent",
                "amount": Decimal("200000"),
                "due_date": TODAY + timedelta(days=5),
                "priority": "1_critical",
                "target_type": "business",
            }
        ],
        planned_transactions=[
            {
                "amount": Decimal("300000"),
                "type": "income",
                "created_at": TODAY + timedelta(days=10),
            }
        ],
        hypothesis=HypothesisScoreRequest(
            title="Inventory Sprint",
            role_perspective=RoleTag.COO,
            required_investment=Decimal("200000"),
            time_lag_days=15,
            expected_roi=Decimal("0.50"),
            risk_level=RiskLevel.MEDIUM,
            status="draft",
            days=45,
        ),
    )

    assert result.scorecard.verdict == "approve"
    assert result.scorecard.probability_of_success >= Decimal("90.0")
    assert result.scorecard.payback_days == 15
    assert result.scorecard.safe_corridor_remaining == Decimal("450000.00")
    assert result.agents[0].agent == "CFO"
    assert result.agents[2].summary == "Probability of success sits at 93.0% with a greenlight recommendation."


def test_scoring_engine_holds_when_liquidity_is_overrun() -> None:
    result = ScoringEngine.evaluate(
        today=TODAY,
        business_balance=Decimal("250000"),
        reserve_buffer=Decimal("50000"),
        obligations=[],
        planned_transactions=[],
        hypothesis=HypothesisScoreRequest(
            title="New kiosk launch",
            role_perspective=RoleTag.COO,
            required_investment=Decimal("300000"),
            time_lag_days=40,
            expected_roi=Decimal("0.20"),
            risk_level=RiskLevel.HIGH,
            status="draft",
            days=45,
        ),
    )

    assert result.scorecard.verdict == "hold"
    assert result.scorecard.probability_of_success == Decimal("5.0")
    assert result.scorecard.runway_label == "outside_corridor"
    assert result.scorecard.safe_corridor_remaining == Decimal("-100000.00")
    assert result.agents[0].stance == "block"
    assert result.agents[1].stance == "block"
