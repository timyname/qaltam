from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from backend.app.models.enums import HypothesisStatus, RiskLevel, RoleTag
from backend.app.schemas.dashboard import HypothesisSimulationResult


class HypothesisCreate(BaseModel):
    title: str
    role_perspective: RoleTag
    required_investment: Decimal
    time_lag_days: int
    expected_roi: Decimal
    risk_level: RiskLevel = RiskLevel.MEDIUM
    status: HypothesisStatus = HypothesisStatus.DRAFT


class HypothesisRead(HypothesisCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class HypothesisScoreRequest(HypothesisCreate):
    days: int = 45


class AgentRationale(BaseModel):
    agent: str
    stance: str
    summary: str
    signals: list[str]


class HypothesisScorecard(BaseModel):
    probability_of_success: Decimal
    verdict: str
    runway_label: str
    cash_pressure_pct: Decimal
    payback_days: int | None
    projected_return_amount: Decimal
    net_return_amount: Decimal
    safe_corridor_remaining: Decimal
    baseline_gap_date: date | None
    scenario_gap_date: date | None
    max_delta_drawdown: Decimal


class HypothesisScoreResponse(BaseModel):
    title: str
    initiator_role: RoleTag
    risk_level: RiskLevel
    scorecard: HypothesisScorecard
    agents: list[AgentRationale]
    simulation: HypothesisSimulationResult
