from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum as SqlEnum
from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.models.enums import RoleTag, TransactionType


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    telegram_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    category: Mapped[str] = mapped_column(String(100), index=True)
    type: Mapped[TransactionType] = mapped_column(SqlEnum(TransactionType), index=True)
    role_tag: Mapped[RoleTag] = mapped_column(SqlEnum(RoleTag), default=RoleTag.CFO)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    account: Mapped["Account"] = relationship(back_populates="transactions")


from backend.app.models.account import Account  # noqa: E402
