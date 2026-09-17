from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Enum as SqlEnum
from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models.enums import AccountType, ObligationPriority


class Obligation(Base):
    __tablename__ = "obligations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(120), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    due_date: Mapped[date] = mapped_column(Date, index=True)
    priority: Mapped[ObligationPriority] = mapped_column(SqlEnum(ObligationPriority), index=True)
    target_type: Mapped[AccountType] = mapped_column(SqlEnum(AccountType), index=True)
