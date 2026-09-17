from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.enums import AccountType, ClientMode, TransactionType
from backend.app.models.profile import UserProfile
from backend.app.models.transaction import Transaction
from backend.app.schemas.ingestion import TransactionDraft
from backend.app.schemas.transaction import QuickAddPayload
from backend.app.services.chat_service import ChatService
from backend.app.services.transaction_parser import TextTransactionParser
from backend.app.services.transaction_service import TransactionService

BUSINESS_HINTS = {
    "avans",
    "biz",
    "business",
    "client",
    "company",
    "corp",
    "inventory",
    "kassa",
    "kaspi",
    "nalog",
    "office",
    "parts",
    "rent",
    "sale",
    "sales",
    "salary",
    "supplier",
    "tax",
    "warehouse",
    "выруч",
    "касса",
    "клиент",
    "компания",
    "налог",
    "аренда",
    "зарплат",
    "аванс",
}


@dataclass(slots=True)
class QuickAddResult:
    transaction: Transaction
    account_type: AccountType
    route: str
    normalized_text: str
    message: str


class QuickAddService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.chat = ChatService(session)
        self.transactions = TransactionService(session)
        self.classifier = self.chat.classifier

    async def create(self, payload: QuickAddPayload) -> QuickAddResult:
        if payload.raw_text and payload.raw_text.strip():
            return await self._create_from_text(payload)
        return await self._create_from_structured(payload)

    async def _create_from_text(self, payload: QuickAddPayload) -> QuickAddResult:
        normalized_text = " ".join(payload.raw_text.strip().split())
        profile = await self._profile(payload)
        draft = TextTransactionParser.parse(normalized_text)
        route = "text_parser"
        if draft is None:
            draft = await self.classifier.classify_text(normalized_text)
            route = "llm_classifier"
        if draft is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Text could not be parsed into a transaction.",
            )

        if payload.note:
            draft = draft.model_copy(update={"note": payload.note})

        account_type = self._resolve_account_type(
            profile=profile,
            explicit_account_type=payload.account_type,
            draft=draft,
        )
        transaction = await self.transactions.create_from_draft(
            draft,
            account_type,
            telegram_user_id=payload.telegram_user_id,
        )
        await self.session.commit()
        return QuickAddResult(
            transaction=transaction,
            account_type=account_type,
            route=route,
            normalized_text=normalized_text,
            message=self._build_message(transaction, account_type),
        )

    async def _create_from_structured(self, payload: QuickAddPayload) -> QuickAddResult:
        profile = await self._profile(payload)
        transaction_type = payload.transaction_type or TransactionType.EXPENSE
        category = payload.category or "misc"
        source_text = payload.note or f"{payload.amount} {category}"
        draft = TransactionDraft(
            amount=payload.amount,
            category=category,
            transaction_type=transaction_type,
            note=payload.note,
            source_text=source_text,
        )
        account_type = self._resolve_account_type(
            profile=profile,
            explicit_account_type=payload.account_type,
            draft=draft,
        )
        transaction = await self.transactions.create_from_draft(
            draft,
            account_type,
            telegram_user_id=payload.telegram_user_id,
        )
        await self.session.commit()
        return QuickAddResult(
            transaction=transaction,
            account_type=account_type,
            route="structured",
            normalized_text=source_text,
            message=self._build_message(transaction, account_type),
        )

    async def _profile(self, payload: QuickAddPayload) -> UserProfile | None:
        if payload.telegram_user_id is None:
            return None
        telegram_chat_id = payload.telegram_chat_id or payload.telegram_user_id
        return await self.chat.get_or_create_profile(payload.telegram_user_id, telegram_chat_id)

    @staticmethod
    def _resolve_account_type(
        *,
        profile: UserProfile | None,
        explicit_account_type: AccountType | None,
        draft: TransactionDraft,
    ) -> AccountType:
        if explicit_account_type is not None:
            return explicit_account_type
        if profile is not None:
            if profile.client_mode == ClientMode.BUSINESS:
                return AccountType.BUSINESS
            if profile.client_mode == ClientMode.PERSONAL:
                return AccountType.PERSONAL
        normalized = f"{draft.category} {draft.source_text}".lower()
        if draft.transaction_type == TransactionType.INCOME:
            return AccountType.BUSINESS
        if any(token in normalized for token in BUSINESS_HINTS):
            return AccountType.BUSINESS
        return AccountType.PERSONAL

    @staticmethod
    def _build_message(transaction: Transaction, account_type: AccountType) -> str:
        direction = "Income" if transaction.type == TransactionType.INCOME else "Expense"
        return f"{direction} saved: {transaction.category} {transaction.amount} -> {account_type.value}"
