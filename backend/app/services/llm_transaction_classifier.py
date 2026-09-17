from __future__ import annotations

from decimal import Decimal, InvalidOperation

from backend.app.models.enums import TransactionType
from backend.app.schemas.ingestion import TransactionDraft
from backend.app.services.deepseek_client import DeepSeekClient


class LlmTransactionClassifier:
    def __init__(self, client: DeepSeekClient | None = None) -> None:
        self.client = client or DeepSeekClient()

    async def classify_text(self, text: str) -> TransactionDraft | None:
        if not self.client.api_key or not text.strip():
            return None

        system_prompt = (
            "You classify short finance messages into JSON. "
            "Return only JSON with keys: amount, category, transaction_type, note. "
            "transaction_type must be either income or expense. "
            "amount must be a numeric string without currency symbols. "
            "If the message is not a transaction, return {\"amount\": null, \"category\": null, "
            "\"transaction_type\": null, \"note\": \"not_transaction\"}."
        )
        result = await self.client.extract_json(system_prompt, text)
        if not result or not result.json_data:
            return None

        payload = result.json_data
        amount = payload.get("amount")
        category = payload.get("category")
        transaction_type = payload.get("transaction_type")
        if amount in (None, "") or not category or transaction_type not in {"income", "expense"}:
            return None

        try:
            parsed_amount = Decimal(str(amount))
        except (InvalidOperation, TypeError, ValueError):
            return None

        return TransactionDraft(
            amount=parsed_amount,
            category=str(category).strip().lower(),
            transaction_type=TransactionType(str(transaction_type).lower()),
            note=payload.get("note") or text,
            source_text=text,
            confidence=0.75,
        )
