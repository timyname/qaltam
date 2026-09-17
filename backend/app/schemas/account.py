from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from backend.app.models.enums import AccountType


class AccountDetailBase(BaseModel):
    bank_name: str | None = None
    iban: str | None = None
    account_number: str | None = None
    currency: str = "KZT"
    owner_label: str | None = None
    note: str | None = None


class AccountCreate(BaseModel):
    name: str
    type: AccountType
    balance: Decimal = Decimal("0")
    details: AccountDetailBase | None = None


class AccountRead(AccountCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
