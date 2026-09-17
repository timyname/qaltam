from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.db.base import Base
from backend.app.models.account import Account
from backend.app.models.enums import AccountType, ClientMode, ObligationPriority, RiskLevel, TransactionType
from backend.app.models.obligation import Obligation
from backend.app.models.profile import ImportedStatement, UserProfile
from backend.app.models.transaction import Transaction
from backend.app.services.dashboard_service import DashboardService
from backend.app.services.memory_service import MemoryService
from backend.app.services.receipt_service import ReceiptService


@pytest.mark.asyncio
async def test_dashboard_service_returns_macro_medium_and_micro_views():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        profile = UserProfile(
            telegram_user_id=77,
            telegram_chat_id=88,
            display_name="Aruzhan",
            client_mode=ClientMode.MIXED,
            risk_level=RiskLevel.MEDIUM,
            preferred_language="ru",
            communication_style=None,
            owner_priority=None,
            privacy_policy_note="local only",
            onboarding_step="completed",
            onboarding_completed=True,
            memory_summary=None,
        )
        session.add(profile)
        await session.flush()

        business_account = Account(name="Business Pocket", type=AccountType.BUSINESS, balance=Decimal("520000"))
        personal_account = Account(name="Personal Pocket", type=AccountType.PERSONAL, balance=Decimal("180000"))
        session.add_all([business_account, personal_account])
        await session.flush()

        now = datetime.now(timezone.utc)
        session.add_all(
            [
                Transaction(
                    account_id=business_account.id,
                    amount=Decimal("150000"),
                    category="sales_income",
                    type=TransactionType.INCOME,
                    note="Client payment",
                    created_at=now - timedelta(days=5),
                ),
                Transaction(
                    account_id=business_account.id,
                    amount=Decimal("45000"),
                    category="inventory_parts",
                    type=TransactionType.EXPENSE,
                    note="Supplier transfer",
                    created_at=now - timedelta(days=2),
                ),
                Transaction(
                    account_id=personal_account.id,
                    amount=Decimal("12000"),
                    category="family_living",
                    type=TransactionType.EXPENSE,
                    note="Groceries",
                    created_at=now - timedelta(days=1),
                ),
            ]
        )
        session.add(
            Obligation(
                title="Rent",
                amount=Decimal("80000"),
                due_date=date.today() + timedelta(days=4),
                priority=ObligationPriority.CRITICAL,
                target_type=AccountType.BUSINESS,
            )
        )
        session.add(
            ImportedStatement(
                source_name="Kaspi",
                file_path="telegram://statement/77/demo.csv",
                original_filename="demo.csv",
                telegram_user_id=77,
                parse_status="clarification_required",
                raw_content="demo",
                note="parsed=3 auto=2 unclear=1",
            )
        )
        await session.flush()

        memory = MemoryService(session)
        await memory.save_pending_statement(
            77,
            {
                "statement_id": 1,
                "parsed_count": 3,
                "auto_count": 2,
                "current_index": 0,
                "items": [
                    {
                        "index": 1,
                        "statement_date": date.today().isoformat(),
                        "amount": "45000",
                        "transaction_type": "expense",
                        "counterparty": "Arman T.",
                        "description": "Transfer",
                        "reason": "Ambiguous supplier/person transfer",
                        "suggested_account_type": "business",
                        "suggested_life_sector": "inventory_parts",
                        "matched_rules": [
                            {
                                "match_key": "arman-t",
                                "account_type": "business",
                                "life_sector": "inventory_parts",
                                "explanation": "Arman T. is a supplier.",
                            }
                        ],
                    }
                ],
            },
        )
        await memory.save_clarification_rule(
            77,
            match_key="arman-t",
            account_type="business",
            life_sector="inventory_parts",
            explanation="Arman T. is a supplier.",
        )
        receipt_service = ReceiptService(session)
        older_receipt = receipt_service.analyze_text(
            "\n".join(
                [
                    "MAGNUM EXPRESS",
                    "BANAN 2 x 450 900",
                    "MILK 1 x 620 620",
                    "TOTAL 1520",
                ]
            )
        )
        assert older_receipt is not None
        older_receipt.purchased_at = older_receipt.purchased_at - timedelta(days=10)
        await receipt_service.persist_receipt(telegram_user_id=77, receipt=older_receipt)

        latest_receipt = receipt_service.analyze_text(
            "\n".join(
                [
                    "MAGNUM EXPRESS",
                    "BANAN 2 x 510 1020",
                    "MILK 1 x 650 650",
                    "TOTAL 1670",
                ]
            )
        )
        assert latest_receipt is not None
        await receipt_service.persist_receipt(telegram_user_id=77, receipt=latest_receipt)
        await session.commit()

        service = DashboardService(session)
        macro = await service.get_macro_dashboard()
        medium = await service.get_medium_dashboard()
        micro = await service.get_micro_dashboard(77)

        assert macro.imported_statements_total == 1
        assert macro.clarification_open_total == 1
        assert macro.business_balance == Decimal("520000")
        assert any(item.slug == "sales_income" and item.amount == Decimal("150000") for item in macro.bridge_totals)

        assert medium.safe_to_withdraw.available_business_balance == Decimal("520000")
        assert len(medium.projection) == 30
        assert medium.recent_receipts_total == 2
        assert medium.recent_receipts_amount == Decimal("3190")
        assert medium.tracked_skus_total == 2
        assert any(item.sku_key == "banan" and item.price_change_pct == Decimal("13.33") for item in medium.inflation_leaders)
        assert medium.last_receipt is not None
        assert medium.last_receipt.total_amount == Decimal("1670")
        assert medium.recent_transactions[0].category == "family_living"

        assert micro.profile_name == "Aruzhan"
        assert micro.pending_clarification is not None
        assert micro.pending_clarification.current_item.counterparty == "Arman T."
        assert micro.pending_clarification.current_item.matched_rules[0].match_key == "arman-t"
        assert micro.recent_rules[0].life_sector == "inventory_parts"
        assert micro.last_import is not None
        assert micro.last_import.original_filename == "demo.csv"

    await engine.dispose()
