from datetime import date, timedelta
from decimal import Decimal

from app.services.financial_engine import FinancialEngine


TODAY = date(2026, 7, 26)


def test_safe_to_withdraw_respects_reserve_and_obligations():
    result = FinancialEngine.get_safe_to_withdraw(
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
            },
            {
                "title": "Payroll",
                "amount": Decimal("250000"),
                "due_date": TODAY + timedelta(days=12),
                "priority": "1_critical",
                "target_type": "business",
            },
        ],
        planned_transactions=[
            {
                "amount": Decimal("300000"),
                "type": "income",
                "created_at": TODAY + timedelta(days=3),
            },
            {
                "amount": Decimal("50000"),
                "type": "expense",
                "created_at": TODAY + timedelta(days=10),
            },
        ],
        days=30,
    )

    assert result.safe_amount == Decimal("650000")
    assert result.projected_gap_date is None
    assert result.upcoming_obligations_total == Decimal("450000")


def test_detects_first_cash_gap_date_when_projection_turns_negative():
    gap_date = FinancialEngine.get_cash_gap_date(
        today=TODAY,
        opening_balance=Decimal("100000"),
        obligations=[
            {
                "title": "Tax",
                "amount": Decimal("130000"),
                "due_date": TODAY + timedelta(days=4),
                "priority": "1_critical",
                "target_type": "business",
            }
        ],
        planned_transactions=[],
        days=30,
    )

    assert gap_date == TODAY + timedelta(days=4)


def test_builds_thirty_day_projection_points():
    points = FinancialEngine.project_cashflow(
        today=TODAY,
        opening_balance=Decimal("500000"),
        obligations=[
            {
                "title": "Salary",
                "amount": Decimal("200000"),
                "due_date": TODAY + timedelta(days=7),
                "priority": "1_critical",
                "target_type": "business",
            }
        ],
        planned_transactions=[
            {
                "amount": Decimal("400000"),
                "type": "income",
                "created_at": TODAY + timedelta(days=2),
            }
        ],
        days=30,
    )

    assert len(points) == 30
    assert points[0].opening_balance == Decimal("500000")
    assert points[2].inflow == Decimal("400000")
    assert points[7].outflow == Decimal("200000")
    assert points[-1].closing_balance == Decimal("700000")


def test_simulates_hypothesis_with_lagged_return_and_payback():
    simulation = FinancialEngine.simulate_hypothesis(
        today=TODAY,
        opening_balance=Decimal("800000"),
        obligations=[],
        planned_transactions=[],
        hypothesis={
            "title": "Inventory Sprint",
            "role_perspective": "COO",
            "required_investment": Decimal("200000"),
            "time_lag_days": 20,
            "expected_roi": Decimal("0.50"),
            "risk_level": "medium",
        },
        days=45,
    )

    assert len(simulation.baseline_curve) == 45
    assert simulation.hypothesis_curve[0].closing_balance == Decimal("600000")
    assert simulation.hypothesis_curve[20].inflow == Decimal("300000")
    assert simulation.payback_date == TODAY + timedelta(days=20)


def test_generates_eleven_gap_scenarios_ranked_by_urgency():
    scenarios = FinancialEngine.get_gap_scenarios(
        projected_gap_days=5,
        deficit_amount=Decimal("350000"),
        available_reserve=Decimal("100000"),
    )

    assert len(scenarios) == 11
    assert scenarios[0].title == "Freeze non-critical expenses"
    assert scenarios[0].urgency == "urgent"
    assert scenarios[-1].title == "Activate short-term bridge financing"
