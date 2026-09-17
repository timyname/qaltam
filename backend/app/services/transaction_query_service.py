from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.account import Account
from backend.app.models.enums import AccountType, TransactionType
from backend.app.models.transaction import Transaction
from backend.app.schemas.transaction import TransactionQueryResponse
from backend.app.services.deepseek_client import DeepSeekClient

_STOPWORDS = {
    "а",
    "бар",
    "без",
    "бы",
    "в",
    "во",
    "все",
    "где",
    "да",
    "до",
    "за",
    "и",
    "из",
    "или",
    "какие",
    "какой",
    "как",
    "когда",
    "ли",
    "мне",
    "на",
    "но",
    "о",
    "по",
    "посчитай",
    "покажи",
    "сколько",
    "траты",
    "ушло",
    "что",
    "это",
}


@dataclass(slots=True)
class TransactionQueryIntent:
    category_hint: str | None
    direction: TransactionType
    account_type: AccountType | None
    days_back: int | None
    period_start: date | None
    period_end: date | None
    route: str
    source: str


class TransactionQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.deepseek = DeepSeekClient()

    async def answer_question(self, *, question: str, telegram_user_id: int) -> TransactionQueryResponse:
        normalized_question = " ".join(question.strip().split())
        intent = await self._interpret(normalized_question)
        period_start, period_end = self._resolve_period(intent)
        transactions = await self._matched_transactions(
            telegram_user_id=telegram_user_id,
            intent=intent,
            period_start=period_start,
            period_end=period_end,
            question=normalized_question,
        )
        total_amount = sum((Decimal(str(item.amount)) for item in transactions), Decimal("0"))
        matched_categories = sorted({item.category for item in transactions})
        answer = await self._compose_answer(
            question=normalized_question,
            total_amount=total_amount,
            transaction_count=len(transactions),
            matched_categories=matched_categories,
            period_start=period_start,
            period_end=period_end,
        )
        return TransactionQueryResponse(
            answer=answer,
            total_amount=total_amount,
            transaction_count=len(transactions),
            matched_categories=matched_categories,
            period_start=period_start,
            period_end=period_end,
            route=intent.route,
            source=intent.source,
        )

    async def _matched_transactions(
        self,
        *,
        telegram_user_id: int,
        intent: TransactionQueryIntent,
        period_start: date | None,
        period_end: date | None,
        question: str,
    ) -> list[Transaction]:
        statement = (
            select(Transaction)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Transaction.telegram_user_id == telegram_user_id,
                Transaction.type == intent.direction,
            )
            .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        )
        if intent.account_type is not None:
            statement = statement.where(Account.type == intent.account_type)
        if period_start is not None:
            statement = statement.where(
                Transaction.created_at >= datetime.combine(period_start, time.min, tzinfo=timezone.utc)
            )
        if period_end is not None:
            statement = statement.where(
                Transaction.created_at <= datetime.combine(period_end, time.max, tzinfo=timezone.utc)
            )
        result = await self.session.execute(statement)
        rows = list(result.scalars().all())
        tokens = self._query_tokens(intent.category_hint or question)
        if not tokens:
            return rows

        matched: list[Transaction] = []
        for transaction in rows:
            haystack = " ".join(
                part for part in [transaction.category, transaction.note or ""] if part
            ).lower()
            if any(token in haystack for token in tokens):
                matched.append(transaction)
        return matched

    async def _interpret(self, question: str) -> TransactionQueryIntent:
        if self.deepseek.api_key:
            response = await self.deepseek.extract_json(
                system_prompt=(
                    "You normalize finance questions into JSON with keys: "
                    "category_hint, direction, account_type, days_back, period_start, period_end. "
                    "direction must be expense or income. account_type must be business, personal, or null. "
                    "Use null when the user did not specify a period or account lane."
                ),
                user_prompt=question,
            )
            data = response.json_data if response else None
            if data is not None:
                return TransactionQueryIntent(
                    category_hint=self._clean_hint(data.get("category_hint")),
                    direction=self._parse_direction(data.get("direction")),
                    account_type=self._parse_account_type(data.get("account_type")),
                    days_back=self._parse_int(data.get("days_back")),
                    period_start=self._parse_date(data.get("period_start")),
                    period_end=self._parse_date(data.get("period_end")),
                    route="deepseek_intent",
                    source="deepseek",
                )

        lowered = question.lower()
        account_type = None
        if any(token in lowered for token in ("бизнес", "касса", "company", "business")):
            account_type = AccountType.BUSINESS
        if any(token in lowered for token in ("личн", "сем", "personal", "family")):
            account_type = AccountType.PERSONAL

        days_back = 30 if any(token in lowered for token in ("месяц", "month", "30 дн", "30дн")) else None
        return TransactionQueryIntent(
            category_hint=self._clean_hint(question),
            direction=TransactionType.INCOME if any(token in lowered for token in ("доход", "income", "пришло")) else TransactionType.EXPENSE,
            account_type=account_type,
            days_back=days_back,
            period_start=None,
            period_end=None,
            route="heuristic_intent",
            source="heuristic",
        )

    async def _compose_answer(
        self,
        *,
        question: str,
        total_amount: Decimal,
        transaction_count: int,
        matched_categories: list[str],
        period_start: date | None,
        period_end: date | None,
    ) -> str:
        if self.deepseek.api_key:
            response = await self.deepseek.extract_json(
                system_prompt=(
                    "You summarize finance totals in one short sentence. "
                    "Return JSON with a single key answer. "
                    "Mention the computed amount exactly as given and the number of matched transactions."
                ),
                user_prompt=(
                    f"Question: {question}\n"
                    f"Amount: {total_amount}\n"
                    f"Transactions: {transaction_count}\n"
                    f"Categories: {', '.join(matched_categories) or 'none'}\n"
                    f"Period start: {period_start}\n"
                    f"Period end: {period_end}"
                ),
            )
            if response and response.json_data and isinstance(response.json_data.get("answer"), str):
                answer = response.json_data["answer"].strip()
                if answer:
                    return answer

        category_summary = ", ".join(matched_categories[:3]) if matched_categories else "подходящих категорий"
        if transaction_count == 0:
            return f"По запросу «{question}» транзакции не найдены."
        return (
            f"По запросу «{question}» найдено {transaction_count} операций на сумму {total_amount} KZT "
            f"по категориям: {category_summary}."
        )

    @staticmethod
    def _resolve_period(intent: TransactionQueryIntent) -> tuple[date | None, date | None]:
        if intent.period_start or intent.period_end:
            return intent.period_start, intent.period_end
        if intent.days_back is None:
            return None, None
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=max(intent.days_back - 1, 0))
        return start_date, end_date

    @staticmethod
    def _parse_direction(value: object) -> TransactionType:
        if str(value or "").strip().lower() == "income":
            return TransactionType.INCOME
        return TransactionType.EXPENSE

    @staticmethod
    def _parse_account_type(value: object) -> AccountType | None:
        normalized = str(value or "").strip().lower()
        if normalized == "business":
            return AccountType.BUSINESS
        if normalized == "personal":
            return AccountType.PERSONAL
        return None

    @staticmethod
    def _parse_int(value: object) -> int | None:
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _parse_date(value: object) -> date | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None

    @staticmethod
    def _query_tokens(value: str) -> list[str]:
        parts = re.findall(r"[0-9A-Za-zА-Яа-яЁёІіЇїЄєҚқӘәҒғҢңҰұҮүҺһ]{2,}", value.lower())
        tokens: list[str] = []
        for part in parts:
            if part in _STOPWORDS:
                continue
            if part not in tokens:
                tokens.append(part)
        return tokens

    @staticmethod
    def _clean_hint(value: object) -> str | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        return raw
