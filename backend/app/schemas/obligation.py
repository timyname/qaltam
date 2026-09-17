from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from backend.app.models.enums import AccountType, ObligationPriority


class ObligationCreate(BaseModel):
    title: str
    amount: Decimal
    due_date: date
    priority: ObligationPriority
    target_type: AccountType


class ObligationRead(ObligationCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
