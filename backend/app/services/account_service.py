from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.account import Account, AccountDetail
from backend.app.models.enums import AccountType
from backend.app.schemas.account import AccountCreate
from backend.app.schemas.ingestion import AccountDraft


class AccountService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_default_account(
        self,
        account_type: AccountType,
        *,
        telegram_user_id: int | None,
    ) -> Account:
        result = await self.session.execute(
            select(Account)
            .where(Account.type == account_type, Account.telegram_user_id == telegram_user_id)
            .order_by(Account.id.asc())
        )
        account = result.scalars().first()
        if account:
            return account
        name = "Personal Pocket" if account_type == AccountType.PERSONAL else "Business Pocket"
        account = Account(
            telegram_user_id=telegram_user_id,
            name=name,
            type=account_type,
            balance=Decimal("0"),
        )
        self.session.add(account)
        await self.session.flush()
        return account

    async def create_account(self, payload: AccountCreate, *, telegram_user_id: int | None = None) -> Account:
        account = Account(
            telegram_user_id=telegram_user_id,
            name=payload.name,
            type=payload.type,
            balance=payload.balance,
        )
        self.session.add(account)
        await self.session.flush()
        if payload.details:
            detail = AccountDetail(account_id=account.id, **payload.details.model_dump())
            self.session.add(detail)
        return account

    async def create_account_from_draft(
        self,
        draft: AccountDraft,
        account_type: AccountType,
        *,
        telegram_user_id: int | None = None,
    ) -> Account:
        account = Account(
            telegram_user_id=telegram_user_id,
            name=draft.name,
            type=account_type,
            balance=draft.balance,
        )
        self.session.add(account)
        await self.session.flush()
        return account
