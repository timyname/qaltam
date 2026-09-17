from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, model_validator

from backend.app.models.enums import AccountType, RoleTag, TransactionType


class TransactionCreate(BaseModel):
    account_id: int
    amount: Decimal
    category: str
    type: TransactionType
    role_tag: RoleTag = RoleTag.CFO
    note: str | None = None
    created_at: datetime | None = None


class TransactionRead(TransactionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class QuickAddPayload(BaseModel):
    raw_text: str | None = None
    telegram_user_id: int | None = None
    telegram_chat_id: int | None = None
    amount: Decimal | None = None
    category: str | None = None
    account_type: AccountType | None = None
    transaction_type: TransactionType | None = TransactionType.EXPENSE
    note: str | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "QuickAddPayload":
        if self.raw_text and self.raw_text.strip():
            return self
        if self.amount is None or not self.category or self.account_type is None:
            raise ValueError("Provide raw_text or amount + category + account_type.")
        return self


class QuickAddResponse(BaseModel):
    transaction: TransactionRead
    account_type: AccountType
    route: str
    normalized_text: str
    message: str


class TransactionQueryPayload(BaseModel):
    question: str
    telegram_user_id: int
    telegram_chat_id: int | None = None


class TransactionQueryResponse(BaseModel):
    answer: str
    total_amount: Decimal
    transaction_count: int
    matched_categories: list[str]
    period_start: date | None = None
    period_end: date | None = None
    route: str
    source: str
