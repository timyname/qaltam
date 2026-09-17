from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class ProjectionPoint(BaseModel):
    date: date
    opening_balance: Decimal
    inflow: Decimal
    outflow: Decimal
    closing_balance: Decimal


class SafeToWithdrawResult(BaseModel):
    safe_amount: Decimal
    reserve_buffer: Decimal
    projected_gap_date: date | None
    available_business_balance: Decimal
    upcoming_obligations_total: Decimal


class GapScenario(BaseModel):
    order: int
    title: str
    action: str
    urgency: str
    estimated_impact: Decimal
    reversible: bool


class HypothesisSimulationResult(BaseModel):
    title: str
    role_perspective: str
    risk_level: str
    payback_date: date | None
    baseline_curve: list[ProjectionPoint]
    hypothesis_curve: list[ProjectionPoint]
    delta_curve: list[ProjectionPoint]


class AccountBalanceSnapshot(BaseModel):
    account_type: str
    label: str
    balance: Decimal


class LifeSectorSummary(BaseModel):
    slug: str
    label: str
    amount: Decimal
    transaction_count: int


class InflationTrackerSummary(BaseModel):
    sku_key: str
    sku_name: str
    category: str
    latest_price: Decimal
    previous_price: Decimal | None
    price_change_pct: Decimal | None
    latest_seen_at: datetime
    merchant_name: str | None = None


class ReceiptItemSummary(BaseModel):
    sku_name: str
    category: str
    quantity: Decimal
    unit_price: Decimal
    total_price: Decimal


class ReceiptSummary(BaseModel):
    id: int
    merchant_name: str | None
    currency: str
    total_amount: Decimal
    purchased_at: datetime
    parsed_status: str
    items: list[ReceiptItemSummary]


class RecentTransactionSummary(BaseModel):
    id: int
    account_name: str
    account_type: str
    transaction_type: str
    category: str
    amount: Decimal
    created_at: datetime
    note: str | None = None


class ImportedStatementSummary(BaseModel):
    id: int
    source_name: str
    original_filename: str | None
    imported_at: datetime
    parse_status: str
    note: str | None = None


class ClarificationQueueItem(BaseModel):
    index: int
    statement_date: date
    amount: Decimal
    transaction_type: str
    counterparty: str
    description: str
    reason: str
    suggested_account_type: str | None = None
    suggested_life_sector: str | None = None
    matched_rules: list["ClarificationRuleSummary"] = []


class PendingClarificationSummary(BaseModel):
    statement_id: int
    parsed_count: int
    auto_count: int
    remaining_count: int
    current_item: ClarificationQueueItem


class ClarificationRuleSummary(BaseModel):
    match_key: str
    account_type: str
    life_sector: str
    explanation: str


class DashboardMacroResponse(BaseModel):
    as_of: date
    total_balance: Decimal
    business_balance: Decimal
    personal_balance: Decimal
    monthly_income: Decimal
    monthly_expense: Decimal
    account_balances: list[AccountBalanceSnapshot]
    bridge_totals: list[LifeSectorSummary]
    imported_statements_total: int
    clarification_open_total: int


class DashboardMediumResponse(BaseModel):
    as_of: date
    safe_to_withdraw: SafeToWithdrawResult
    projection: list[ProjectionPoint]
    gap_scenarios: list[GapScenario]
    obligations_total: Decimal
    recent_receipts_total: int
    recent_receipts_amount: Decimal
    tracked_skus_total: int
    inflation_leaders: list[InflationTrackerSummary]
    last_receipt: ReceiptSummary | None
    recent_transactions: list[RecentTransactionSummary]


class DashboardMicroResponse(BaseModel):
    as_of: datetime
    profile_name: str | None
    preferred_language: str | None
    onboarding_completed: bool | None
    pending_clarification: PendingClarificationSummary | None
    recent_rules: list[ClarificationRuleSummary]
    last_import: ImportedStatementSummary | None
    webapp_url: str
    quick_add_path: str
