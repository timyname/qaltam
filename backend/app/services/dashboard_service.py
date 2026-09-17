from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.models.account import Account
from backend.app.models.enums import AccountType, TransactionType
from backend.app.models.obligation import Obligation
from backend.app.models.profile import ImportedStatement, UserProfile
from backend.app.models.transaction import Transaction
from backend.app.schemas.dashboard import (
    AccountBalanceSnapshot,
    ClarificationQueueItem,
    ClarificationRuleSummary,
    DashboardMacroResponse,
    DashboardMediumResponse,
    DashboardMicroResponse,
    InflationTrackerSummary,
    ImportedStatementSummary,
    LifeSectorSummary,
    PendingClarificationSummary,
    RecentTransactionSummary,
    ReceiptItemSummary,
    ReceiptSummary,
)
from backend.app.services.financial_engine import FinancialEngine
from backend.app.services.life_sectors import LIFE_SECTORS
from backend.app.services.memory_service import MemoryService
from backend.app.services.receipt_service import ReceiptService


class DashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.memory = MemoryService(session)
        self.receipts = ReceiptService(session)
        self.settings = get_settings()

    async def get_macro_dashboard(self, telegram_user_id: int | None = None) -> DashboardMacroResponse:
        today = date.today()
        accounts = await self._accounts(telegram_user_id)
        transactions = await self._transactions(telegram_user_id)
        statements = await self._statements(telegram_user_id)
        recent_transactions = self._recent_window(transactions, today=today)

        total_balance = self._sum_amount(account.balance for account in accounts)
        business_balance = self._sum_amount(
            account.balance for account in accounts if account.type == AccountType.BUSINESS
        )
        personal_balance = self._sum_amount(
            account.balance for account in accounts if account.type == AccountType.PERSONAL
        )
        monthly_income = self._sum_amount(
            transaction.amount for transaction in recent_transactions if transaction.type == TransactionType.INCOME
        )
        monthly_expense = self._sum_amount(
            transaction.amount for transaction in recent_transactions if transaction.type == TransactionType.EXPENSE
        )

        return DashboardMacroResponse(
            as_of=today,
            total_balance=total_balance,
            business_balance=business_balance,
            personal_balance=personal_balance,
            monthly_income=monthly_income,
            monthly_expense=monthly_expense,
            account_balances=[
                AccountBalanceSnapshot(
                    account_type=account.type.value,
                    label=account.name,
                    balance=Decimal(account.balance),
                )
                for account in sorted(accounts, key=lambda item: item.id)
            ],
            bridge_totals=self._bridge_totals(recent_transactions),
            imported_statements_total=len(statements),
            clarification_open_total=sum(
                1 for statement in statements if statement.parse_status == "clarification_required"
            ),
        )

    async def get_medium_dashboard(self, telegram_user_id: int | None = None) -> DashboardMediumResponse:
        today = date.today()
        accounts = await self._accounts(telegram_user_id)
        obligations = await self._obligations()
        transactions = await self._transactions(telegram_user_id)
        projection_inputs = self._projection_transactions(transactions, today=today)
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
        business_balance = self._sum_amount(
            account.balance for account in accounts if account.type == AccountType.BUSINESS
        )

        safe_to_withdraw = FinancialEngine.get_safe_to_withdraw(
            today=today,
            business_balance=business_balance,
            reserve_buffer=Decimal(self.settings.safe_withdrawal_buffer),
            obligations=obligations_payload,
            planned_transactions=projection_inputs,
            days=30,
        )
        projection = FinancialEngine.project_cashflow(
            today=today,
            opening_balance=business_balance,
            obligations=obligations_payload,
            planned_transactions=projection_inputs,
            days=30,
        )
        minimum_closing_balance = min((point.closing_balance for point in projection), default=Decimal("0"))
        deficit_amount = abs(min(minimum_closing_balance, Decimal("0")))
        projected_gap_days = None
        if safe_to_withdraw.projected_gap_date:
            projected_gap_days = (safe_to_withdraw.projected_gap_date - today).days

        accounts_by_id = {account.id: account for account in accounts}
        recent_transactions = sorted(transactions, key=lambda item: item.created_at, reverse=True)[:8]
        receipt_insights = await self.receipts.get_insights(days=60, telegram_user_id=telegram_user_id)
        return DashboardMediumResponse(
            as_of=today,
            safe_to_withdraw=safe_to_withdraw,
            projection=projection,
            gap_scenarios=FinancialEngine.get_gap_scenarios(
                projected_gap_days=projected_gap_days,
                deficit_amount=deficit_amount,
                available_reserve=Decimal(self.settings.safe_withdrawal_buffer),
            ),
            obligations_total=self._sum_amount(item.amount for item in obligations),
            recent_receipts_total=receipt_insights.recent_receipts_total,
            recent_receipts_amount=receipt_insights.recent_receipts_amount,
            tracked_skus_total=receipt_insights.tracked_skus_total,
            inflation_leaders=[
                InflationTrackerSummary(
                    sku_key=item.sku_key,
                    sku_name=item.sku_name,
                    category=item.category,
                    latest_price=item.latest_price,
                    previous_price=item.previous_price,
                    price_change_pct=item.price_change_pct,
                    latest_seen_at=item.latest_seen_at,
                    merchant_name=item.merchant_name,
                )
                for item in receipt_insights.inflation_leaders
            ],
            last_receipt=(
                ReceiptSummary(
                    id=receipt_insights.last_receipt.id,
                    merchant_name=receipt_insights.last_receipt.merchant_name,
                    currency=receipt_insights.last_receipt.currency,
                    total_amount=receipt_insights.last_receipt.total_amount,
                    purchased_at=receipt_insights.last_receipt.purchased_at,
                    parsed_status=receipt_insights.last_receipt.parsed_status,
                    items=[
                        ReceiptItemSummary(
                            sku_name=item.sku_name,
                            category=item.category,
                            quantity=item.quantity,
                            unit_price=item.unit_price,
                            total_price=item.total_price,
                        )
                        for item in receipt_insights.last_receipt.items
                    ],
                )
                if receipt_insights.last_receipt
                else None
            ),
            recent_transactions=[
                RecentTransactionSummary(
                    id=transaction.id,
                    account_name=accounts_by_id.get(transaction.account_id).name
                    if accounts_by_id.get(transaction.account_id)
                    else "Unknown account",
                    account_type=accounts_by_id.get(transaction.account_id).type.value
                    if accounts_by_id.get(transaction.account_id)
                    else "unknown",
                    transaction_type=transaction.type.value,
                    category=transaction.category,
                    amount=Decimal(transaction.amount),
                    created_at=transaction.created_at,
                    note=transaction.note,
                )
                for transaction in recent_transactions
            ],
        )

    async def get_micro_dashboard(self, telegram_user_id: int | None = None) -> DashboardMicroResponse:
        profile = await self._profile(telegram_user_id)
        effective_user_id = telegram_user_id or (profile.telegram_user_id if profile else None)
        pending = (
            await self.memory.get_pending_statement(effective_user_id)
            if effective_user_id is not None
            else None
        )
        recent_rules = (
            await self.memory.get_clarification_rules(effective_user_id, limit=5)
            if effective_user_id is not None
            else []
        )
        last_import = await self._last_import(effective_user_id)

        return DashboardMicroResponse(
            as_of=datetime.now(timezone.utc),
            profile_name=profile.display_name if profile and profile.display_name else None,
            preferred_language=profile.preferred_language if profile else None,
            onboarding_completed=profile.onboarding_completed if profile else None,
            pending_clarification=self._pending_summary(pending),
            recent_rules=[
                ClarificationRuleSummary(
                    match_key=str(rule.get("match_key") or ""),
                    account_type=str(rule.get("account_type") or ""),
                    life_sector=str(rule.get("life_sector") or ""),
                    explanation=str(rule.get("explanation") or ""),
                )
                for rule in recent_rules
                if rule.get("match_key")
            ],
            last_import=last_import,
            webapp_url=self.settings.telegram_webapp_url,
            quick_add_path="/api/v1/transactions",
        )

    async def _accounts(self, telegram_user_id: int | None = None) -> list[Account]:
        query = select(Account).order_by(Account.id.asc())
        if telegram_user_id is not None:
            query = query.where(Account.telegram_user_id == telegram_user_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def _transactions(self, telegram_user_id: int | None = None) -> list[Transaction]:
        query = select(Transaction).order_by(Transaction.created_at.asc(), Transaction.id.asc())
        if telegram_user_id is not None:
            query = query.where(Transaction.telegram_user_id == telegram_user_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def _obligations(self) -> list[Obligation]:
        result = await self.session.execute(select(Obligation).order_by(Obligation.due_date.asc(), Obligation.id.asc()))
        return list(result.scalars().all())

    async def _statements(self, telegram_user_id: int | None = None) -> list[ImportedStatement]:
        query = select(ImportedStatement).order_by(ImportedStatement.imported_at.desc(), ImportedStatement.id.desc())
        if telegram_user_id is not None:
            query = query.where(ImportedStatement.telegram_user_id == telegram_user_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def _profile(self, telegram_user_id: int | None) -> UserProfile | None:
        if telegram_user_id is None:
            return None
        result = await self.session.execute(
            select(UserProfile)
            .where(UserProfile.telegram_user_id == telegram_user_id)
            .order_by(UserProfile.id.asc())
        )
        return result.scalars().first()

    async def _last_import(self, telegram_user_id: int | None) -> ImportedStatementSummary | None:
        query = select(ImportedStatement).order_by(ImportedStatement.imported_at.desc(), ImportedStatement.id.desc())
        if telegram_user_id is not None:
            query = query.where(ImportedStatement.telegram_user_id == telegram_user_id)
        result = await self.session.execute(query.limit(1))
        statement = result.scalars().first()
        if not statement:
            return None
        return ImportedStatementSummary(
            id=statement.id,
            source_name=statement.source_name,
            original_filename=statement.original_filename,
            imported_at=statement.imported_at,
            parse_status=statement.parse_status,
            note=statement.note,
        )

    @staticmethod
    def _sum_amount(values) -> Decimal:
        total = Decimal("0")
        for value in values:
            total += Decimal(value)
        return total

    @staticmethod
    def _recent_window(transactions: list[Transaction], *, today: date) -> list[Transaction]:
        window_start = today - timedelta(days=29)
        return [item for item in transactions if item.created_at.date() >= window_start]

    def _bridge_totals(self, transactions: list[Transaction]) -> list[LifeSectorSummary]:
        buckets = {
            item["slug"]: {"label": item["label"], "amount": Decimal("0"), "transaction_count": 0}
            for item in LIFE_SECTORS
        }
        for transaction in transactions:
            slug = self._map_life_sector(transaction)
            bucket = buckets.get(slug)
            if not bucket:
                continue
            bucket["amount"] += Decimal(transaction.amount)
            bucket["transaction_count"] += 1

        return [
            LifeSectorSummary(
                slug=slug,
                label=str(payload["label"]),
                amount=payload["amount"],
                transaction_count=int(payload["transaction_count"]),
            )
            for slug, payload in buckets.items()
        ]

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

    @staticmethod
    def _pending_summary(payload: dict | None) -> PendingClarificationSummary | None:
        if not payload or not payload.get("items"):
            return None
        current_index = int(payload.get("current_index", 0))
        items = payload["items"]
        if current_index >= len(items):
            return None
        current_item = items[current_index]
        return PendingClarificationSummary(
            statement_id=int(payload["statement_id"]),
            parsed_count=int(payload["parsed_count"]),
            auto_count=int(payload["auto_count"]),
            remaining_count=max(0, len(items) - current_index),
            current_item=ClarificationQueueItem(
                index=int(current_item["index"]),
                statement_date=date.fromisoformat(current_item["statement_date"]),
                amount=Decimal(str(current_item["amount"])),
                transaction_type=str(current_item["transaction_type"]),
                counterparty=str(current_item["counterparty"]),
                description=str(current_item["description"]),
                reason=str(current_item["reason"]),
                suggested_account_type=current_item.get("suggested_account_type"),
                suggested_life_sector=current_item.get("suggested_life_sector"),
                matched_rules=[
                    ClarificationRuleSummary(
                        match_key=str(rule.get("match_key") or ""),
                        account_type=str(rule.get("account_type") or ""),
                        life_sector=str(rule.get("life_sector") or ""),
                        explanation=str(rule.get("explanation") or ""),
                    )
                    for rule in current_item.get("matched_rules", [])
                ],
            ),
        )

    @staticmethod
    def _map_life_sector(transaction: Transaction) -> str:
        category = transaction.category.lower()
        note = (transaction.note or "").lower()
        text = f"{category} {note}"
        keyword_map = {
            "inventory_parts": ("inventory", "parts", "supplier", "stock"),
            "payroll_team": ("payroll", "salary", "team", "staff"),
            "rent_utilities": ("rent", "utility", "office", "electric"),
            "logistics_transport": ("delivery", "logistics", "fuel", "taxi", "transport"),
            "marketing_growth": ("marketing", "ads", "promotion", "target"),
            "taxes_fees": ("tax", "vat", "fee", "duty"),
            "tools_software": ("software", "tool", "subscription", "saas"),
            "owner_draw": ("owner", "draw", "withdrawal"),
            "family_living": ("family", "home", "food", "living", "kids"),
            "savings_debt": ("saving", "debt", "loan", "reserve"),
        }
        for slug, tokens in keyword_map.items():
            if any(token in text for token in tokens):
                return slug
        if transaction.type == TransactionType.INCOME:
            return "sales_income"
        if transaction.type == TransactionType.EXPENSE and "personal" in text:
            return "family_living"
        return "tools_software"
