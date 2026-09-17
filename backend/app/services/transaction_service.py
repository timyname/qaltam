from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.enums import AccountType, RoleTag, TransactionType
from backend.app.models.transaction import Transaction
from backend.app.schemas.ingestion import TransactionDraft
from backend.app.services.account_service import AccountService


class TransactionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.accounts = AccountService(session)

    async def create_from_draft(
        self,
        draft: TransactionDraft,
        account_type_hint: AccountType,
        *,
        telegram_user_id: int | None = None,
    ) -> Transaction:
        return await self.create_transaction(
            amount=Decimal(draft.amount),
            category=draft.category,
            transaction_type=draft.transaction_type,
            account_type_hint=account_type_hint,
            note=draft.note,
            created_at=getattr(draft, "created_at", None),
            telegram_user_id=telegram_user_id,
        )

    async def create_transaction(
        self,
        *,
        amount: Decimal,
        category: str,
        transaction_type: TransactionType,
        account_type_hint: AccountType,
        note: str | None = None,
        created_at: datetime | None = None,
        role_tag: RoleTag = RoleTag.CFO,
        telegram_user_id: int | None = None,
    ) -> Transaction:
        account = await self.accounts.get_or_create_default_account(
            account_type_hint,
            telegram_user_id=telegram_user_id,
        )
        signed_amount = amount if transaction_type == TransactionType.INCOME else -amount
        account.balance = Decimal(account.balance) + signed_amount
        transaction = Transaction(
            account_id=account.id,
            telegram_user_id=telegram_user_id,
            amount=amount,
            category=category,
            type=transaction_type,
            role_tag=role_tag,
            note=note,
            created_at=created_at or datetime.now(timezone.utc),
        )
        self.session.add(transaction)
        await self.session.flush()
        return transaction
