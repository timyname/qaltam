from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.models.account import Account
from backend.app.models.enums import AccountType, RiskLevel
from backend.app.models.obligation import Obligation
from backend.app.models.transaction import Transaction
from backend.app.schemas.dashboard import HypothesisSimulationResult, ProjectionPoint
from backend.app.schemas.hypothesis import (
    AgentRationale,
    HypothesisScoreRequest,
    HypothesisScoreResponse,
    HypothesisScorecard,
)
from backend.app.services.financial_engine import FinancialEngine


class ScoringEngine:
    @staticmethod
    def evaluate(
        *,
        today: date,
        business_balance: Decimal,
        reserve_buffer: Decimal,
        obligations: list[dict],
        planned_transactions: list[dict],
        hypothesis: HypothesisScoreRequest,
    ) -> HypothesisScoreResponse:
        expected_roi = ScoringEngine._normalize_roi(Decimal(hypothesis.expected_roi))
        normalized_hypothesis = {
            "title": hypothesis.title,
            "role_perspective": hypothesis.role_perspective.value,
            "required_investment": Decimal(hypothesis.required_investment),
            "time_lag_days": int(hypothesis.time_lag_days),
            "expected_roi": expected_roi,
            "risk_level": hypothesis.risk_level.value,
        }

        safe_to_withdraw = FinancialEngine.get_safe_to_withdraw(
            today=today,
            business_balance=business_balance,
            reserve_buffer=reserve_buffer,
            obligations=obligations,
            planned_transactions=planned_transactions,
            days=30,
        )
        simulation = FinancialEngine.simulate_hypothesis(
            today=today,
            opening_balance=business_balance,
            obligations=obligations,
            planned_transactions=planned_transactions,
            hypothesis=normalized_hypothesis,
            days=hypothesis.days,
        )

        investment = Decimal(hypothesis.required_investment)
        projected_return_amount = (investment * (Decimal("1") + expected_roi)).quantize(Decimal("0.01"))
        net_return_amount = (investment * expected_roi).quantize(Decimal("0.01"))
        safe_corridor_remaining = (safe_to_withdraw.safe_amount - investment).quantize(Decimal("0.01"))
        cash_pressure_pct = ScoringEngine._percent(investment, safe_to_withdraw.available_business_balance)
        baseline_gap_date = ScoringEngine._first_negative_date(simulation.baseline_curve)
        scenario_gap_date = ScoringEngine._first_negative_date(simulation.hypothesis_curve)
        max_delta_drawdown = min(
            (point.closing_balance for point in simulation.delta_curve),
            default=Decimal("0"),
        ).quantize(Decimal("0.01"))
        payback_days = (
            (simulation.payback_date - today).days
            if simulation.payback_date
            else None
        )

        probability_of_success = ScoringEngine._probability_of_success(
            expected_roi=expected_roi,
            payback_days=payback_days,
            safe_corridor_remaining=safe_corridor_remaining,
            cash_pressure_pct=cash_pressure_pct,
            baseline_gap_date=baseline_gap_date,
            scenario_gap_date=scenario_gap_date,
            risk_level=hypothesis.risk_level,
        )
        runway_label = ScoringEngine._runway_label(safe_corridor_remaining)
        verdict = ScoringEngine._verdict(
            probability_of_success=probability_of_success,
            safe_corridor_remaining=safe_corridor_remaining,
            scenario_gap_date=scenario_gap_date,
            baseline_gap_date=baseline_gap_date,
        )

        return HypothesisScoreResponse(
            title=hypothesis.title,
            initiator_role=hypothesis.role_perspective,
            risk_level=hypothesis.risk_level,
            scorecard=HypothesisScorecard(
                probability_of_success=probability_of_success,
                verdict=verdict,
                runway_label=runway_label,
                cash_pressure_pct=cash_pressure_pct,
                payback_days=payback_days,
                projected_return_amount=projected_return_amount,
                net_return_amount=net_return_amount,
                safe_corridor_remaining=safe_corridor_remaining,
                baseline_gap_date=baseline_gap_date,
                scenario_gap_date=scenario_gap_date,
                max_delta_drawdown=max_delta_drawdown,
            ),
            agents=ScoringEngine._build_agent_rationales(
                today=today,
                hypothesis=hypothesis,
                probability_of_success=probability_of_success,
                verdict=verdict,
                runway_label=runway_label,
                safe_corridor_remaining=safe_corridor_remaining,
                cash_pressure_pct=cash_pressure_pct,
                payback_days=payback_days,
                baseline_gap_date=baseline_gap_date,
                scenario_gap_date=scenario_gap_date,
                projected_return_amount=projected_return_amount,
                max_delta_drawdown=max_delta_drawdown,
            ),
            simulation=simulation,
        )

    @staticmethod
    def _probability_of_success(
        *,
        expected_roi: Decimal,
        payback_days: int | None,
        safe_corridor_remaining: Decimal,
        cash_pressure_pct: Decimal,
        baseline_gap_date: date | None,
        scenario_gap_date: date | None,
        risk_level: RiskLevel,
    ) -> Decimal:
        score = Decimal("54")
        score += min(Decimal("22"), max(Decimal("0"), expected_roi * Decimal("36")))

        if payback_days is None:
            score -= Decimal("10")
        elif payback_days <= 14:
            score += Decimal("14")
        elif payback_days <= 21:
            score += Decimal("10")
        elif payback_days <= 30:
            score += Decimal("6")
        elif payback_days <= 45:
            score += Decimal("2")
        else:
            score -= Decimal("6")

        if safe_corridor_remaining >= 0:
            score += Decimal("10")
            if safe_corridor_remaining >= Decimal("100000"):
                score += Decimal("4")
        else:
            score -= min(
                Decimal("26"),
                Decimal("8") + (abs(safe_corridor_remaining) / max(abs(safe_corridor_remaining), Decimal("1"))) * Decimal("18"),
            )

        if cash_pressure_pct > Decimal("40"):
            score -= min(Decimal("18"), (cash_pressure_pct - Decimal("40")) * Decimal("0.30"))
        elif cash_pressure_pct < Decimal("22"):
            score += Decimal("4")

        risk_penalties = {
            RiskLevel.LOW: Decimal("0"),
            RiskLevel.MEDIUM: Decimal("7"),
            RiskLevel.HIGH: Decimal("15"),
        }
        score -= risk_penalties[risk_level]

        if scenario_gap_date and not baseline_gap_date:
            score -= Decimal("18")
        elif scenario_gap_date and baseline_gap_date and scenario_gap_date < baseline_gap_date:
            score -= Decimal("12")
        elif scenario_gap_date is None and baseline_gap_date is not None:
            score += Decimal("6")

        return min(Decimal("95"), max(Decimal("5"), score)).quantize(Decimal("0.1"))

    @staticmethod
    def _verdict(
        *,
        probability_of_success: Decimal,
        safe_corridor_remaining: Decimal,
        scenario_gap_date: date | None,
        baseline_gap_date: date | None,
    ) -> str:
        if (
            probability_of_success >= Decimal("72")
            and safe_corridor_remaining >= 0
            and (scenario_gap_date is None or baseline_gap_date == scenario_gap_date)
        ):
            return "approve"
        if probability_of_success >= Decimal("48") and safe_corridor_remaining >= Decimal("-75000"):
            return "stage"
        return "hold"

    @staticmethod
    def _runway_label(safe_corridor_remaining: Decimal) -> str:
        if safe_corridor_remaining >= Decimal("100000"):
            return "inside_corridor"
        if safe_corridor_remaining >= 0:
            return "tight_corridor"
        return "outside_corridor"

    @staticmethod
    def _build_agent_rationales(
        *,
        today: date,
        hypothesis: HypothesisScoreRequest,
        probability_of_success: Decimal,
        verdict: str,
        runway_label: str,
        safe_corridor_remaining: Decimal,
        cash_pressure_pct: Decimal,
        payback_days: int | None,
        baseline_gap_date: date | None,
        scenario_gap_date: date | None,
        projected_return_amount: Decimal,
        max_delta_drawdown: Decimal,
    ) -> list[AgentRationale]:
        cfo_stance = "support" if safe_corridor_remaining >= 0 and scenario_gap_date is None else "watch"
        if safe_corridor_remaining < 0:
            cfo_stance = "block"

        if safe_corridor_remaining >= 0:
            cfo_summary = (
                f"Funding stays within the safe withdrawal corridor by {safe_corridor_remaining.quantize(Decimal('0.01'))} KZT."
            )
        else:
            cfo_summary = (
                f"The scenario overruns the safe corridor by {abs(safe_corridor_remaining).quantize(Decimal('0.01'))} KZT."
            )

        cfo_signals = [
            f"Cash pressure uses {cash_pressure_pct.quantize(Decimal('0.1'))}% of the live business balance.",
            (
                f"Scenario gap lands on {scenario_gap_date.isoformat()}."
                if scenario_gap_date
                else "No scenario cash gap appears inside the forecast horizon."
            ),
            (
                f"Payback is projected in {payback_days} days."
                if payback_days is not None
                else "Payback is not visible inside the current forecast horizon."
            ),
        ]

        coo_stance = "support" if payback_days is not None and payback_days <= 30 and cash_pressure_pct <= 45 else "watch"
        if cash_pressure_pct >= 70 or hypothesis.risk_level == RiskLevel.HIGH:
            coo_stance = "block"

        coo_summary = (
            "Execution load looks manageable for a contained experiment."
            if coo_stance == "support"
            else "Execution should be staged against milestones and cash checkpoints."
            if coo_stance == "watch"
            else "Operational load is heavy enough that this should wait or be phased."
        )
        coo_signals = [
            f"Initiator lens: {hypothesis.role_perspective.value}.",
            f"Risk level is set to {hypothesis.risk_level.value}.",
            f"Funds stay deployed for {hypothesis.time_lag_days} days before return arrives.",
        ]

        arbiter_stance = "support" if verdict == "approve" else "watch" if verdict == "stage" else "block"
        verdict_phrase = {
            "approve": "greenlight",
            "stage": "staged rollout",
            "hold": "hold",
        }[verdict]
        gap_delta = None
        if baseline_gap_date and scenario_gap_date:
            gap_delta = (scenario_gap_date - baseline_gap_date).days

        arbiter_summary = (
            f"Probability of success sits at {probability_of_success}% with a {verdict_phrase} recommendation."
        )
        arbiter_signals = [
            f"Projected gross return reaches {projected_return_amount.quantize(Decimal('0.01'))} KZT.",
            f"Maximum downside swing versus baseline is {max_delta_drawdown.quantize(Decimal('0.01'))} KZT.",
            (
                "The scenario keeps the same gap profile as baseline."
                if baseline_gap_date == scenario_gap_date
                else f"The scenario shifts the gap by {gap_delta} days."
                if gap_delta is not None
                else "The scenario changes the cash-gap profile inside the planning window."
            ),
        ]

        return [
            AgentRationale(agent="CFO", stance=cfo_stance, summary=cfo_summary, signals=cfo_signals),
            AgentRationale(agent="COO", stance=coo_stance, summary=coo_summary, signals=coo_signals),
            AgentRationale(agent="Arbiter", stance=arbiter_stance, summary=arbiter_summary, signals=arbiter_signals),
        ]

    @staticmethod
    def _first_negative_date(points: list[ProjectionPoint]) -> date | None:
        for point in points:
            if point.closing_balance < 0:
                return point.date
        return None

    @staticmethod
    def _normalize_roi(value: Decimal) -> Decimal:
        if value > Decimal("3"):
            return (value / Decimal("100")).quantize(Decimal("0.0001"))
        return value.quantize(Decimal("0.0001"))

    @staticmethod
    def _percent(numerator: Decimal, denominator: Decimal) -> Decimal:
        base = max(Decimal(denominator), Decimal("1"))
        return ((Decimal(numerator) / base) * Decimal("100")).quantize(Decimal("0.1"))


class HypothesisScoringService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()

    async def preview(self, payload: HypothesisScoreRequest) -> HypothesisScoreResponse:
        today = date.today()
        accounts = await self._accounts()
        obligations = await self._obligations()
        transactions = await self._transactions()
        business_balance = sum(
            (Decimal(account.balance) for account in accounts if account.type == AccountType.BUSINESS),
            start=Decimal("0"),
        )

        obligations_payload = [
            {
                "title": item.title,
                "amount": Decimal(item.amount),
                "due_date": item.due_date,
                "priority": item.priority.value,
                "target_type": item.target_type.value,
            }
            for item in obligations
        ]
        planned_transactions = self._projection_transactions(transactions, today=today)

        return ScoringEngine.evaluate(
            today=today,
            business_balance=business_balance,
            reserve_buffer=Decimal(self.settings.safe_withdrawal_buffer),
            obligations=obligations_payload,
            planned_transactions=planned_transactions,
            hypothesis=payload,
        )

    async def _accounts(self) -> list[Account]:
        result = await self.session.execute(select(Account).order_by(Account.id.asc()))
        return list(result.scalars().all())

    async def _obligations(self) -> list[Obligation]:
        result = await self.session.execute(select(Obligation).order_by(Obligation.due_date.asc(), Obligation.id.asc()))
        return list(result.scalars().all())

    async def _transactions(self) -> list[Transaction]:
        result = await self.session.execute(select(Transaction).order_by(Transaction.created_at.asc(), Transaction.id.asc()))
        return list(result.scalars().all())

    @staticmethod
    def _projection_transactions(transactions: list[Transaction], *, today: date) -> list[dict]:
        window_start = today - timedelta(days=29)
        projected: list[dict] = []
        for transaction in transactions:
            original_date = transaction.created_at.date()
            if original_date < window_start:
                continue
            offset = max(0, (original_date - window_start).days)
            projected.append(
                {
                    "amount": Decimal(transaction.amount),
                    "type": transaction.type.value,
                    "created_at": today + timedelta(days=offset),
                }
            )
        return projected
