from __future__ import annotations

import re
from decimal import Decimal

from backend.app.models.enums import TransactionType
from backend.app.schemas.ingestion import TransactionDraft


INCOME_MARKERS = {
    "income",
    "\u043f\u043e\u0441\u0442\u0443\u043f",
    "\u043f\u043e\u043f\u043e\u043b\u043d",
    "\u0437\u0430\u0440\u043f\u043b\u0430\u0442",
    "\u0432\u044b\u0440\u0443\u0447\u043a",
    "\u043f\u043e\u043b\u0443\u0447\u0438\u043b",
    "received",
    "income+",
}

EXPENSE_MARKERS = {
    "expense",
    "\u0440\u0430\u0441\u0445\u043e\u0434",
    "\u043f\u043e\u0442\u0440\u0430\u0442",
    "\u0435\u0434\u0430",
    "\u0442\u0430\u043a\u0441\u0438",
    "\u043e\u043f\u043b\u0430\u0442",
    "spent",
}

STOP_WORDS = {
    "\u043f\u043e\u0441\u0442\u0443\u043f\u043b\u0435\u043d\u0438\u0435",
    "\u043f\u043e\u0441\u0442\u0443\u043f\u0438\u043b",
    "\u043f\u043e\u0441\u0442\u0443\u043f\u0438\u043b\u0430",
    "\u043f\u043e\u0441\u0442\u0443\u043f\u0438\u043b\u0438",
    "income",
    "income+",
    "\u0434\u043e\u0445\u043e\u0434",
    "\u0432\u044b\u0440\u0443\u0447\u043a\u0430",
    "\u043f\u043e\u043b\u0443\u0447\u0438\u043b",
    "\u043f\u043e\u043b\u0443\u0447\u0438\u043b\u0430",
    "received",
    "\u0440\u0430\u0441\u0445\u043e\u0434",
    "expense",
    "\u043e\u043f\u043b\u0430\u0442\u0430",
    "\u043e\u043f\u043b\u0430\u0442\u0438\u043b",
    "\u043e\u043f\u043b\u0430\u0442\u0438\u043b\u0430",
    "spent",
    "\u043f\u043e\u0442\u0440\u0430\u0442\u0438\u043b",
    "\u043f\u043e\u0442\u0440\u0430\u0442\u0438\u043b\u0430",
}


class TextTransactionParser:
    amount_pattern = re.compile(r"(?P<sign>[+-])?(?P<amount>\d[\d\s.,]*)")

    @classmethod
    def parse(cls, text: str) -> TransactionDraft | None:
        normalized = " ".join(text.strip().split())
        if not normalized:
            return None
        match = cls.amount_pattern.search(normalized)
        if not match:
            return None
        amount = cls._to_decimal(match.group("amount"))
        before = normalized[: match.start()].strip()
        after = normalized[match.end() :].strip()
        category = cls._extract_category(before, after)
        transaction_type = cls._infer_type(normalized, match.group("sign"))
        return TransactionDraft(
            amount=amount,
            category=category,
            transaction_type=transaction_type,
            note=normalized,
            source_text=normalized,
            confidence=0.9,
        )

    @staticmethod
    def _to_decimal(raw_amount: str) -> Decimal:
        cleaned = raw_amount.replace(" ", "").replace(",", ".")
        return Decimal(cleaned)

    @staticmethod
    def _extract_category(before: str, after: str) -> str:
        candidate = after or before
        candidate = candidate.replace("-", " ")
        tokens = [token for token in candidate.split() if token]
        if not tokens:
            return "\u043f\u0440\u043e\u0447\u0435\u0435"
        cleaned_tokens = [token for token in tokens if token.lower() not in STOP_WORDS]
        if cleaned_tokens:
            return cleaned_tokens[0].lower()
        return tokens[-1].lower()

    @staticmethod
    def _infer_type(text: str, sign: str | None) -> TransactionType:
        lowered = text.lower()
        if sign == "+":
            return TransactionType.INCOME
        if sign == "-":
            return TransactionType.EXPENSE
        if any(marker in lowered for marker in INCOME_MARKERS):
            return TransactionType.INCOME
        if any(marker in lowered for marker in EXPENSE_MARKERS):
            return TransactionType.EXPENSE
        return TransactionType.EXPENSE
