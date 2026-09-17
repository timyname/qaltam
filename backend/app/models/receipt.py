from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_path: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    merchant_name: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(8), default="KZT")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    purchased_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    parsed_status: Mapped[str] = mapped_column(String(30), default="parsed", index=True)
    raw_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    items: Mapped[list["ReceiptItem"]] = relationship(
        back_populates="receipt",
        cascade="all, delete-orphan",
        order_by="ReceiptItem.id.asc()",
    )


class ReceiptItem(Base):
    __tablename__ = "receipt_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id"), index=True)
    sku_name: Mapped[str] = mapped_column(String(160), index=True)
    sku_key: Mapped[str] = mapped_column(String(160), index=True)
    category: Mapped[str] = mapped_column(String(80), default="general", index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    total_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))

    receipt: Mapped["Receipt"] = relationship(back_populates="items")

