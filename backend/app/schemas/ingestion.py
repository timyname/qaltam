from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from backend.app.models.enums import TransactionType


class TransactionDraft(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    amount: Decimal
    category: str
    transaction_type: TransactionType
    note: str | None = None
    source_text: str
    confidence: float = 0.85


class IngestionOutcome(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    normalized_text: str
    response_text: str
    route: str
    transaction: TransactionDraft | None = None
    onboarding_step: str | None = None


@dataclass(slots=True)
class AccountDraft:
    name: str
    balance: Decimal
    raw_text: str

