from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ReceiptItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku_name: str
    sku_key: str
    category: str
    quantity: Decimal
    unit_price: Decimal
    total_price: Decimal


class ReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    merchant_name: str | None
    currency: str
    total_amount: Decimal
    purchased_at: datetime
    parsed_status: str
    items: list[ReceiptItemRead]


class InflationTrackerItem(BaseModel):
    sku_key: str
    sku_name: str
    category: str
    latest_price: Decimal
    previous_price: Decimal | None
    price_change_pct: Decimal | None
    latest_seen_at: datetime
    merchant_name: str | None


class ReceiptInsightsResponse(BaseModel):
    recent_receipts_total: int
    recent_receipts_amount: Decimal
    tracked_skus_total: int
    inflation_leaders: list[InflationTrackerItem]
    last_receipt: ReceiptRead | None


class ReceiptUploadResponse(BaseModel):
    message: str
    receipt: ReceiptRead | None
