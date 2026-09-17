from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.receipt import Receipt, ReceiptItem
from backend.app.schemas.receipt import InflationTrackerItem, ReceiptInsightsResponse, ReceiptRead
from backend.app.services.ocr_adapter import OcrAdapter

TOTAL_TOKENS = ("итого", "барлыгы", "барлығы", "total", "tot", "sum")


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(slots=True)
class ParsedReceiptItem:
    sku_name: str
    sku_key: str
    category: str
    quantity: Decimal
    unit_price: Decimal
    total_price: Decimal


@dataclass(slots=True)
class ParsedReceipt:
    merchant_name: str | None
    total_amount: Decimal
    currency: str
    items: list[ParsedReceiptItem]
    purchased_at: datetime
    raw_text: str


class ReceiptService:
    def __init__(self, session: AsyncSession, ocr_adapter: OcrAdapter | None = None) -> None:
        self.session = session
        self.ocr_adapter = ocr_adapter or OcrAdapter()

    def analyze_text(self, raw_text: str) -> ParsedReceipt | None:
        cleaned = raw_text.strip()
        if not cleaned:
            return None

        lines = [self._clean_line(line) for line in cleaned.splitlines() if self._clean_line(line)]
        if len(lines) < 2:
            return None

        merchant_name = self._merchant_name(lines)
        items: list[ParsedReceiptItem] = []
        total_amount: Decimal | None = None
        for line in lines:
            lowered = line.lower()
            if any(token in lowered for token in TOTAL_TOKENS):
                total_amount = self._extract_last_money(line)
                continue
            parsed_item = self._parse_item_line(line)
            if parsed_item:
                items.append(parsed_item)

        if not items and total_amount is None:
            return None

        basket_total = sum((item.total_price for item in items), Decimal("0"))
        resolved_total = total_amount or basket_total
        if resolved_total <= 0:
            return None
        if not items:
            items.append(
                ParsedReceiptItem(
                    sku_name="basket_total",
                    sku_key="basket_total",
                    category="general",
                    quantity=Decimal("1"),
                    unit_price=resolved_total,
                    total_price=resolved_total,
                )
            )
        return ParsedReceipt(
            merchant_name=merchant_name,
            total_amount=resolved_total,
            currency="KZT",
            items=items,
            purchased_at=_utcnow_naive(),
            raw_text=cleaned,
        )

    async def ingest_photo(self, *, telegram_user_id: int, image_path: Path) -> ParsedReceipt | None:
        text = self.ocr_adapter.extract_text(image_path)
        receipt = self.analyze_text(text)
        if not receipt:
            return None
        await self.persist_receipt(telegram_user_id=telegram_user_id, receipt=receipt, source_path=image_path)
        return receipt

    async def persist_receipt(
        self,
        *,
        telegram_user_id: int | None,
        receipt: ParsedReceipt,
        source_path: Path | None = None,
    ) -> Receipt:
        record = Receipt(
            telegram_user_id=telegram_user_id,
            source_path=str(source_path) if source_path else None,
            merchant_name=receipt.merchant_name,
            currency=receipt.currency,
            total_amount=receipt.total_amount,
            purchased_at=receipt.purchased_at,
            parsed_status="parsed" if receipt.items else "summary_only",
            raw_text=receipt.raw_text,
        )
        self.session.add(record)
        await self.session.flush()
        for item in receipt.items:
            self.session.add(
                ReceiptItem(
                    receipt_id=record.id,
                    sku_name=item.sku_name,
                    sku_key=item.sku_key,
                    category=item.category,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    total_price=item.total_price,
                )
            )
        await self.session.flush()
        return record

    async def get_insights(
        self,
        *,
        days: int = 60,
        telegram_user_id: int | None = None,
    ) -> ReceiptInsightsResponse:
        cutoff = _utcnow_naive() - timedelta(days=days)
        receipt_query = select(Receipt).options(selectinload(Receipt.items)).where(Receipt.purchased_at >= cutoff)
        if telegram_user_id is not None:
            receipt_query = receipt_query.where(Receipt.telegram_user_id == telegram_user_id)
        receipt_query = receipt_query.order_by(Receipt.purchased_at.desc(), Receipt.id.desc())
        receipts = list((await self.session.execute(receipt_query)).scalars().all())
        inflation_leaders = self._inflation_leaders(receipts)
        return ReceiptInsightsResponse(
            recent_receipts_total=len(receipts),
            recent_receipts_amount=sum((Decimal(item.total_amount) for item in receipts), Decimal("0")),
            tracked_skus_total=len({sku.sku_key for receipt in receipts for sku in receipt.items}),
            inflation_leaders=inflation_leaders[:8],
            last_receipt=ReceiptRead.model_validate(receipts[0]) if receipts else None,
        )

    async def get_latest_receipt(self, *, telegram_user_id: int | None = None) -> ReceiptRead | None:
        query = select(Receipt).options(selectinload(Receipt.items)).order_by(Receipt.purchased_at.desc(), Receipt.id.desc())
        if telegram_user_id is not None:
            query = query.where(Receipt.telegram_user_id == telegram_user_id)
        result = await self.session.execute(query.limit(1))
        receipt = result.scalars().first()
        return ReceiptRead.model_validate(receipt) if receipt else None

    def dominant_category(self, receipt: ParsedReceipt) -> str:
        category_totals: dict[str, Decimal] = {}
        for item in receipt.items:
            category_totals[item.category] = category_totals.get(item.category, Decimal("0")) + item.total_price
        if not category_totals:
            return "receipt"
        return max(category_totals.items(), key=lambda pair: pair[1])[0]

    @staticmethod
    def _clean_line(line: str) -> str:
        return re.sub(r"\s+", " ", line).strip(" -:")

    @staticmethod
    def _merchant_name(lines: list[str]) -> str | None:
        for line in lines[:3]:
            if any(char.isalpha() for char in line) and not re.search(r"\d{3,}", line):
                return line[:120]
        return None

    def _parse_item_line(self, line: str) -> ParsedReceiptItem | None:
        numeric_tokens = re.findall(r"\d+(?:[.,]\d+)?", line)
        if len(numeric_tokens) < 1:
            return None
        money_values = [self._to_decimal(token) for token in numeric_tokens if self._to_decimal(token) is not None]
        if not money_values:
            return None
        total_price = money_values[-1]
        if total_price <= 0:
            return None
        quantity = Decimal("1")
        unit_price = total_price
        if len(money_values) >= 2:
            prev = money_values[-2]
            if prev > 0 and prev <= total_price:
                unit_price = prev
                derived_quantity = total_price / prev
                if derived_quantity >= 1 and derived_quantity <= 50:
                    quantity = derived_quantity.quantize(Decimal("0.001")).normalize()
        label = re.sub(r"\d+(?:[.,]\d+)?", " ", line)
        label = re.sub(r"[xх*]+", " ", label, flags=re.IGNORECASE)
        tokens = [token for token in re.split(r"[^A-Za-zА-Яа-я0-9]+", label) if token]
        if not tokens:
            return None
        name = " ".join(tokens[:6]).strip()
        if len(name) < 2:
            return None
        if name.lower() in TOTAL_TOKENS:
            return None
        sku_key = self._sku_key(name)
        return ParsedReceiptItem(
            sku_name=name,
            sku_key=sku_key,
            category=self._category_for_name(name),
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price,
        )

    @staticmethod
    def _extract_last_money(line: str) -> Decimal | None:
        numeric_tokens = re.findall(r"\d+(?:[.,]\d+)?", line)
        if not numeric_tokens:
            return None
        return ReceiptService._to_decimal(numeric_tokens[-1])

    @staticmethod
    def _to_decimal(raw: str) -> Decimal | None:
        try:
            return Decimal(raw.replace(",", "."))
        except (InvalidOperation, AttributeError):
            return None

    @staticmethod
    def _sku_key(name: str) -> str:
        cleaned = re.sub(r"[^a-zа-я0-9]+", "-", name.lower(), flags=re.IGNORECASE)
        return cleaned.strip("-")[:160] or "item"

    @staticmethod
    def _category_for_name(name: str) -> str:
        lowered = name.lower()
        category_tokens = {
            "produce": ("banana", "banan", "яблок", "apple", "томат", "огур", "kart", "potato"),
            "dairy": ("milk", "мол", "кефир", "сыр", "cheese", "yogurt"),
            "bread": ("bread", "хлеб", "лаваш", "bun"),
            "meat": ("beef", "гов", "chicken", "кур", "meat", "ет"),
            "household": ("soap", "мыло", "powder", "clean", "салфет", "detergent"),
            "snacks": ("cola", "chips", "сок", "tea", "coffee", "печень", "шокол"),
        }
        for category, tokens in category_tokens.items():
            if any(token in lowered for token in tokens):
                return category
        return "general"

    def _inflation_leaders(self, receipts: list[Receipt]) -> list[InflationTrackerItem]:
        history: dict[str, list[tuple[datetime, ReceiptItem, Receipt]]] = {}
        for receipt in receipts:
            for item in receipt.items:
                history.setdefault(item.sku_key, []).append((receipt.purchased_at, item, receipt))

        leaders: list[InflationTrackerItem] = []
        for sku_key, series in history.items():
            ordered = sorted(series, key=lambda row: row[0], reverse=True)
            latest_date, latest_item, latest_receipt = ordered[0]
            previous_item = ordered[1][1] if len(ordered) > 1 else None
            price_change_pct: Decimal | None = None
            if previous_item and Decimal(previous_item.unit_price) > 0:
                price_change_pct = (
                    (Decimal(latest_item.unit_price) - Decimal(previous_item.unit_price))
                    / Decimal(previous_item.unit_price)
                    * Decimal("100")
                ).quantize(Decimal("0.01"))
            leaders.append(
                InflationTrackerItem(
                    sku_key=sku_key,
                    sku_name=latest_item.sku_name,
                    category=latest_item.category,
                    latest_price=Decimal(latest_item.unit_price),
                    previous_price=Decimal(previous_item.unit_price) if previous_item else None,
                    price_change_pct=price_change_pct,
                    latest_seen_at=latest_date,
                    merchant_name=latest_receipt.merchant_name,
                )
            )
        return sorted(
            leaders,
            key=lambda item: (
                item.price_change_pct if item.price_change_pct is not None else Decimal("-999"),
                item.latest_seen_at,
            ),
            reverse=True,
        )
