from datetime import date, datetime, timedelta
from decimal import Decimal

from backend.app.schemas.dashboard import (
    GapScenario,
    HypothesisSimulationResult,
    ProjectionPoint,
    SafeToWithdrawResult,
)


class FinancialEngine:
    @staticmethod
    def project_cashflow(
        *,
        today: date,
        opening_balance: Decimal,
        obligations: list[dict],
        planned_transactions: list[dict],
        days: int = 30,
    ) -> list[ProjectionPoint]:
        balance = Decimal(opening_balance)
        inflows_by_day = FinancialEngine._group_transactions_by_day(planned_transactions, "income")
        outflows_by_day = FinancialEngine._group_transactions_by_day(planned_transactions, "expense")
        obligations_by_day = FinancialEngine._group_obligations_by_day(obligations)
        projection: list[ProjectionPoint] = []

        for offset in range(days):
            point_date = today + timedelta(days=offset)
            opening = balance
            inflow = inflows_by_day.get(point_date, Decimal("0"))
            outflow = outflows_by_day.get(point_date, Decimal("0")) + obligations_by_day.get(point_date, Decimal("0"))
            closing = opening + inflow - outflow
            projection.append(
                ProjectionPoint(
                    date=point_date,
                    opening_balance=opening,
                    inflow=inflow,
                    outflow=outflow,
                    closing_balance=closing,
                )
            )
            balance = closing

        return projection

    @staticmethod
    def get_cash_gap_date(
        *,
        today: date,
        opening_balance: Decimal,
        obligations: list[dict],
        planned_transactions: list[dict],
        days: int = 30,
    ) -> date | None:
        projection = FinancialEngine.project_cashflow(
            today=today,
            opening_balance=opening_balance,
            obligations=obligations,
            planned_transactions=planned_transactions,
            days=days,
        )
        for point in projection:
            if point.closing_balance < 0:
                return point.date
        return None

    @staticmethod
    def get_safe_to_withdraw(
        *,
        today: date,
        business_balance: Decimal,
        reserve_buffer: Decimal,
        obligations: list[dict],
        planned_transactions: list[dict],
        days: int = 30,
    ) -> SafeToWithdrawResult:
        projection = FinancialEngine.project_cashflow(
            today=today,
            opening_balance=business_balance,
            obligations=obligations,
            planned_transactions=planned_transactions,
            days=days,
        )
        min_closing_balance = min(point.closing_balance for point in projection)
        safe_amount = max(Decimal("0"), min_closing_balance - Decimal(reserve_buffer))
        return SafeToWithdrawResult(
            safe_amount=safe_amount,
            reserve_buffer=Decimal(reserve_buffer),
            projected_gap_date=FinancialEngine.get_cash_gap_date(
                today=today,
                opening_balance=business_balance,
                obligations=obligations,
                planned_transactions=planned_transactions,
                days=days,
            ),
            available_business_balance=Decimal(business_balance),
            upcoming_obligations_total=sum(
                (
                    Decimal(item["amount"])
                    for item in obligations
                    if item.get("target_type") == "business"
                ),
                start=Decimal("0"),
            ),
        )

    @staticmethod
    def simulate_hypothesis(
        *,
        today: date,
        opening_balance: Decimal,
        obligations: list[dict],
        planned_transactions: list[dict],
        hypothesis: dict,
        days: int = 45,
    ) -> HypothesisSimulationResult:
        baseline_curve = FinancialEngine.project_cashflow(
            today=today,
            opening_balance=opening_balance,
            obligations=obligations,
            planned_transactions=planned_transactions,
            days=days,
        )
        scenario_transactions = list(planned_transactions)
        investment = Decimal(hypothesis["required_investment"])
        expected_roi = Decimal(hypothesis["expected_roi"])
        lag_days = int(hypothesis["time_lag_days"])
        scenario_transactions.extend(
            [
                {
                    "amount": investment,
                    "type": "expense",
                    "created_at": today,
                },
                {
                    "amount": investment * (Decimal("1") + expected_roi),
                    "type": "income",
                    "created_at": today + timedelta(days=lag_days),
                },
            ]
        )
        hypothesis_curve = FinancialEngine.project_cashflow(
            today=today,
            opening_balance=opening_balance,
            obligations=obligations,
            planned_transactions=scenario_transactions,
            days=days,
        )
        delta_curve: list[ProjectionPoint] = []
        payback_date: date | None = None

        for baseline, scenario in zip(baseline_curve, hypothesis_curve, strict=True):
            delta_point = ProjectionPoint(
                date=scenario.date,
                opening_balance=scenario.opening_balance - baseline.opening_balance,
                inflow=scenario.inflow - baseline.inflow,
                outflow=scenario.outflow - baseline.outflow,
                closing_balance=scenario.closing_balance - baseline.closing_balance,
            )
            delta_curve.append(delta_point)
            if payback_date is None and scenario.closing_balance >= baseline.closing_balance:
                payback_date = scenario.date

        return HypothesisSimulationResult(
            title=hypothesis["title"],
            role_perspective=hypothesis["role_perspective"],
            risk_level=hypothesis["risk_level"],
            payback_date=payback_date,
            baseline_curve=baseline_curve,
            hypothesis_curve=hypothesis_curve,
            delta_curve=delta_curve,
        )

    @staticmethod
    def get_gap_scenarios(
        *,
        projected_gap_days: int | None,
        deficit_amount: Decimal,
        available_reserve: Decimal,
    ) -> list[GapScenario]:
        urgency = "urgent" if projected_gap_days is not None and projected_gap_days <= 7 else "planned"
        impacts = [
            Decimal("0.12"),
            Decimal("0.10"),
            Decimal("0.09"),
            Decimal("0.10"),
            Decimal("0.08"),
            Decimal("0.07"),
            Decimal("0.08"),
            Decimal("0.07"),
            Decimal("0.10"),
            Decimal("0.09"),
            Decimal("0.10"),
        ]
        titles_actions = [
            ("Freeze non-critical expenses", "Pause all non-essential outgoing payments for the next seven days."),
            ("Delay owner withdrawal", "Keep owner draws frozen until the cash corridor turns positive."),
            ("Renegotiate payment due date", "Ask counterparties to move the nearest due dates to a safer window."),
            ("Accelerate receivables", "Collect open invoices and request partial prepayments from clients."),
            ("Shift spend from business to personal pocket", "Move selected mixed expenses out of the business balance temporarily."),
            ("Convert planned investment to phased spend", "Split larger initiatives into milestones and release cash gradually."),
            ("Pause low-conversion marketing", "Hold campaigns that are not paying back inside the current horizon."),
            ("Split supplier payment", "Negotiate a partial payment now and the remainder after incoming cash lands."),
            ("Use reserve pocket", f"Deploy up to {Decimal(available_reserve)} from internal reserve with a replenishment plan."),
            ("Re-sequence payroll or contractor dates", "Move non-critical contractor payouts behind protected obligations."),
            ("Activate short-term bridge financing", "Prepare a licensed short-term financing option only if internal levers fail."),
        ]
        scenarios: list[GapScenario] = []
        for index, ((title, action), impact_ratio) in enumerate(zip(titles_actions, impacts, strict=True), start=1):
            scenarios.append(
                GapScenario(
                    order=index,
                    title=title,
                    action=action,
                    urgency=urgency if index <= 4 else "planned",
                    estimated_impact=(Decimal(deficit_amount) * impact_ratio).quantize(Decimal("0.01")),
                    reversible=index != 11,
                )
            )
        return scenarios

    @staticmethod
    def _group_obligations_by_day(obligations: list[dict]) -> dict[date, Decimal]:
        grouped: dict[date, Decimal] = {}
        for item in obligations:
            due_date = FinancialEngine._to_date(item["due_date"])
            grouped[due_date] = grouped.get(due_date, Decimal("0")) + Decimal(item["amount"])
        return grouped

    @staticmethod
    def _group_transactions_by_day(transactions: list[dict], transaction_type: str) -> dict[date, Decimal]:
        grouped: dict[date, Decimal] = {}
        for item in transactions:
            if item["type"] != transaction_type:
                continue
            event_date = FinancialEngine._to_date(item["created_at"])
            grouped[event_date] = grouped.get(event_date, Decimal("0")) + Decimal(item["amount"])
        return grouped

    @staticmethod
    def _to_date(value: date | datetime) -> date:
        if isinstance(value, datetime):
            return value.date()
        return value
