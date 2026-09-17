from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import json
import re
import unicodedata

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.enums import AccountType, ClientMode, TransactionType
from backend.app.models.profile import UserProfile
from backend.app.services.deepseek_client import DeepSeekClient
from backend.app.services.life_sectors import LIFE_SECTOR_SLUGS
from backend.app.services.memory_service import MemoryService
from backend.app.services.statement_parser import StatementEntry


@dataclass(slots=True)
class ClassifiedStatementItem:
    index: int
    statement_date: date
    amount: Decimal
    transaction_type: TransactionType
    counterparty: str
    description: str
    account_type: AccountType
    life_sector: str
    rationale: str
    confidence: float
    match_key: str


@dataclass(slots=True)
class UnclearStatementItem:
    index: int
    statement_date: date
    amount: Decimal
    transaction_type: TransactionType
    counterparty: str
    description: str
    reason: str
    suggested_account_type: AccountType | None = None
    suggested_life_sector: str | None = None


@dataclass(slots=True)
class StatementClassificationResult:
    auto_categorized: list[ClassifiedStatementItem]
    unclear_items: list[UnclearStatementItem]


class StatementClassifier:
    def __init__(self, session: AsyncSession, client: DeepSeekClient | None = None) -> None:
        self.session = session
        self.client = client or DeepSeekClient()
        self.memory = MemoryService(session)

    async def classify_entries(
        self,
        profile: UserProfile,
        entries: list[StatementEntry],
        *,
        telegram_user_id: int,
    ) -> StatementClassificationResult:
        rules = await self.memory.get_clarification_rules(telegram_user_id)
        auto_categorized: list[ClassifiedStatementItem] = []
        unresolved: list[tuple[int, StatementEntry]] = []

        for index, entry in enumerate(entries):
            matched_rule = self._match_rule(entry, rules)
            if matched_rule:
                auto_categorized.append(
                    ClassifiedStatementItem(
                        index=index,
                        statement_date=entry.statement_date,
                        amount=entry.amount,
                        transaction_type=entry.transaction_type,
                        counterparty=entry.counterparty,
                        description=entry.description,
                        account_type=AccountType(matched_rule["account_type"]),
                        life_sector=str(matched_rule["life_sector"]),
                        rationale=f"Правило из памяти: {matched_rule.get('explanation', 'знакомый контрагент')}",
                        confidence=0.98,
                        match_key=str(matched_rule["match_key"]),
                    )
                )
            else:
                unresolved.append((index, entry))

        llm_result = await self._classify_with_llm(profile, unresolved)
        auto_categorized.extend(llm_result.auto_categorized)
        return StatementClassificationResult(
            auto_categorized=sorted(auto_categorized, key=lambda item: item.index),
            unclear_items=sorted(llm_result.unclear_items, key=lambda item: item.index),
        )

    async def resolve_manual_answer(
        self,
        profile: UserProfile,
        item: dict,
        answer_text: str,
    ) -> ClassifiedStatementItem:
        account_type, life_sector, explanation = await self._interpret_answer_with_llm(profile, item, answer_text)
        return self._resolved_item_from_pending(
            item,
            account_type=account_type,
            life_sector=life_sector,
            rationale=explanation,
        )

    def resolve_preselected_choice(
        self,
        item: dict,
        *,
        account_type: str,
        life_sector: str,
        rationale: str = "Выбрано через быструю кнопку",
    ) -> ClassifiedStatementItem:
        return self._resolved_item_from_pending(
            item,
            account_type=AccountType(account_type),
            life_sector=life_sector,
            rationale=rationale,
        )

    async def _classify_with_llm(
        self,
        profile: UserProfile,
        unresolved: list[tuple[int, StatementEntry]],
    ) -> StatementClassificationResult:
        if not unresolved:
            return StatementClassificationResult(auto_categorized=[], unclear_items=[])

        if not self.client.api_key:
            return StatementClassificationResult(
                auto_categorized=[],
                unclear_items=[
                    UnclearStatementItem(
                        index=index,
                        statement_date=entry.statement_date,
                        amount=entry.amount,
                        transaction_type=entry.transaction_type,
                        counterparty=entry.counterparty,
                        description=entry.description,
                        reason="Нужна ручная проверка: сервис DeepSeek сейчас недоступен.",
                    )
                    for index, entry in unresolved
                ],
            )

        system_prompt = (
            "You classify Kazakhstan bank statement items into strict JSON. "
            "Use only these life_sector values: sales_income, inventory_parts, payroll_team, "
            "rent_utilities, logistics_transport, marketing_growth, taxes_fees, tools_software, "
            "owner_draw, family_living, savings_debt. "
            "Use only account_type values personal or business. "
            "Return JSON with keys auto_categorized and unclear_items. "
            "Each auto_categorized item must include index, account_type, life_sector, confidence, rationale. "
            "Each unclear_items item must include index, reason, suggested_account_type, suggested_life_sector. "
            "If an item looks like a vague P2P transfer or merchant ambiguity, place it into unclear_items."
        )
        user_prompt = json.dumps(
            {
                "client_mode": profile.client_mode.value,
                "items": [
                    {
                        "index": index,
                        "date": entry.statement_date.isoformat(),
                        "amount": str(entry.amount),
                        "transaction_type": entry.transaction_type.value,
                        "counterparty": entry.counterparty,
                        "description": entry.description,
                    }
                    for index, entry in unresolved
                ],
            },
            ensure_ascii=False,
        )
        result = await self.client.extract_json(system_prompt, user_prompt)
        payload = result.json_data if result and result.json_data else {}

        by_index = {index: entry for index, entry in unresolved}
        auto_items: list[ClassifiedStatementItem] = []
        unclear_items: list[UnclearStatementItem] = []
        handled_indexes: set[int] = set()

        for item in payload.get("auto_categorized", []):
            try:
                index = int(item["index"])
                entry = by_index[index]
                account_type = AccountType(str(item["account_type"]).lower())
                life_sector = str(item["life_sector"]).strip()
                if life_sector not in LIFE_SECTOR_SLUGS:
                    raise ValueError("invalid life sector")
            except Exception:
                continue
            auto_items.append(
                ClassifiedStatementItem(
                    index=index,
                    statement_date=entry.statement_date,
                    amount=entry.amount,
                    transaction_type=entry.transaction_type,
                    counterparty=entry.counterparty,
                    description=entry.description,
                    account_type=account_type,
                    life_sector=life_sector,
                    rationale=str(item.get("rationale") or "Транзакция классифицирована автоматически."),
                    confidence=float(item.get("confidence") or 0.85),
                    match_key=self._build_match_key(entry.counterparty, entry.description),
                )
            )
            handled_indexes.add(index)

        for item in payload.get("unclear_items", []):
            try:
                index = int(item["index"])
                entry = by_index[index]
            except Exception:
                continue
            suggested_account_type = item.get("suggested_account_type")
            suggested_life_sector = item.get("suggested_life_sector")
            unclear_items.append(
                UnclearStatementItem(
                    index=index,
                    statement_date=entry.statement_date,
                    amount=entry.amount,
                    transaction_type=entry.transaction_type,
                    counterparty=entry.counterparty,
                    description=entry.description,
                    reason=str(item.get("reason") or "Нужно уточнение."),
                    suggested_account_type=AccountType(str(suggested_account_type).lower())
                    if suggested_account_type in {"personal", "business"}
                    else None,
                    suggested_life_sector=str(suggested_life_sector) if suggested_life_sector in LIFE_SECTOR_SLUGS else None,
                )
            )
            handled_indexes.add(index)

        for index, entry in unresolved:
            if index in handled_indexes:
                continue
            unclear_items.append(
                UnclearStatementItem(
                    index=index,
                    statement_date=entry.statement_date,
                    amount=entry.amount,
                    transaction_type=entry.transaction_type,
                    counterparty=entry.counterparty,
                    description=entry.description,
                    reason="Модель не смогла уверенно классифицировать операцию.",
                    suggested_account_type=self._default_account_type(profile),
                )
            )

        return StatementClassificationResult(auto_categorized=auto_items, unclear_items=unclear_items)

    async def _interpret_answer_with_llm(
        self,
        profile: UserProfile,
        item: dict,
        answer_text: str,
    ) -> tuple[AccountType, str, str]:
        fallback_account_type = self._fallback_account_type(profile, answer_text)
        fallback_life_sector = self._fallback_life_sector(answer_text, item["description"])
        if not self.client.api_key:
            return fallback_account_type, fallback_life_sector, "Категория определена по ответу пользователя."

        system_prompt = (
            "Convert the user's clarification into strict JSON with keys account_type, life_sector, explanation. "
            "Use only account_type values personal or business. "
            "Use only life_sector values sales_income, inventory_parts, payroll_team, rent_utilities, "
            "logistics_transport, marketing_growth, taxes_fees, tools_software, owner_draw, family_living, savings_debt."
        )
        user_prompt = json.dumps(
            {
                "client_mode": profile.client_mode.value,
                "item": item,
                "answer_text": answer_text,
            },
            ensure_ascii=False,
        )
        result = await self.client.extract_json(system_prompt, user_prompt)
        payload = result.json_data if result and result.json_data else {}
        account_type_value = str(payload.get("account_type") or fallback_account_type.value).lower()
        life_sector_value = str(payload.get("life_sector") or fallback_life_sector)
        explanation = str(payload.get("explanation") or "Категория определена по ответу пользователя.")

        if account_type_value not in {"personal", "business"}:
            account_type_value = fallback_account_type.value
        if life_sector_value not in LIFE_SECTOR_SLUGS:
            life_sector_value = fallback_life_sector
        return AccountType(account_type_value), life_sector_value, explanation

    def _resolved_item_from_pending(
        self,
        item: dict,
        *,
        account_type: AccountType,
        life_sector: str,
        rationale: str,
    ) -> ClassifiedStatementItem:
        return ClassifiedStatementItem(
            index=int(item["index"]),
            statement_date=date.fromisoformat(item["statement_date"]),
            amount=Decimal(str(item["amount"])),
            transaction_type=TransactionType(str(item["transaction_type"])),
            counterparty=str(item["counterparty"]),
            description=str(item["description"]),
            account_type=account_type,
            life_sector=life_sector,
            rationale=rationale,
            confidence=1.0,
            match_key=self._build_match_key(str(item["counterparty"]), str(item["description"])),
        )

    @staticmethod
    def find_related_rules(counterparty: str, description: str, rules: list[dict], *, limit: int = 3) -> list[dict]:
        haystack = StatementClassifier._normalize(f"{counterparty} {description}")
        if not haystack:
            return []

        matched: list[dict] = []
        seen_keys: set[str] = set()
        for rule in rules:
            match_key = StatementClassifier._normalize(str(rule.get("match_key", "")))
            if not match_key or match_key in seen_keys or match_key not in haystack:
                continue
            matched.append(rule)
            seen_keys.add(match_key)
            if len(matched) >= limit:
                break
        return matched

    @staticmethod
    def _match_rule(entry: StatementEntry, rules: list[dict]) -> dict | None:
        candidates = StatementClassifier._rule_match_candidates(entry.counterparty, entry.description)
        for rule in rules:
            match_key = StatementClassifier._normalize(str(rule.get("match_key", "")))
            if match_key and match_key in candidates:
                return rule
        return None

    @staticmethod
    def _rule_match_candidates(counterparty: str, description: str) -> set[str]:
        candidates = {
            StatementClassifier._normalize(counterparty),
            StatementClassifier._normalize(description),
            StatementClassifier._first_tokens(counterparty),
            StatementClassifier._first_tokens(description),
        }
        candidates.discard("")
        return candidates

    @staticmethod
    def _build_match_key(counterparty: str, description: str) -> str:
        base = StatementClassifier._normalize(counterparty) or StatementClassifier._normalize(description)
        return " ".join(base.split()[:3])[:60]

    @staticmethod
    def _first_tokens(value: str, *, limit: int = 3) -> str:
        normalized = StatementClassifier._normalize(value)
        if not normalized:
            return ""
        return " ".join(normalized.split()[:limit])

    @staticmethod
    def _normalize(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        return " ".join("".join(char if char.isalnum() else " " for char in normalized).split())

    @staticmethod
    def _default_account_type(profile: UserProfile) -> AccountType:
        if profile.client_mode == ClientMode.BUSINESS:
            return AccountType.BUSINESS
        return AccountType.PERSONAL

    @staticmethod
    def _fallback_account_type(profile: UserProfile, answer_text: str) -> AccountType:
        lowered = answer_text.lower()
        if "бизнес" in lowered or "рабоч" in lowered:
            return AccountType.BUSINESS
        if "личн" in lowered or "сем" in lowered:
            return AccountType.PERSONAL
        if "business" in lowered or "Р±РёР·РЅРµСЃ" in lowered or "СЂР°Р±РѕС‡" in lowered:
            return AccountType.BUSINESS
        if "personal" in lowered or "Р»РёС‡" in lowered or "family" in lowered or "СЃРµРј" in lowered:
            return AccountType.PERSONAL
        return StatementClassifier._default_account_type(profile)

    @staticmethod
    def _fallback_life_sector(answer_text: str, description: str) -> str:
        lowered = f"{answer_text} {description}".lower()
        if any(token in lowered for token in ("выруч", "доход", "клиент")):
            return "sales_income"
        if any(token in lowered for token in ("товар", "запчаст", "закуп", "постав")):
            return "inventory_parts"
        if any(token in lowered for token in ("зарплат", "команд")):
            return "payroll_team"
        if any(token in lowered for token in ("аренд", "коммун")):
            return "rent_utilities"
        if any(token in lowered for token in ("логист", "достав", "топлив", "транспорт")):
            return "logistics_transport"
        if any(token in lowered for token in ("реклам", "маркет")):
            return "marketing_growth"
        if any(token in lowered for token in ("налог", "комисс", "сбор")):
            return "taxes_fees"
        if any(token in lowered for token in ("софт", "подпис")):
            return "tools_software"
        if any(token in lowered for token in ("владел", "вывод")):
            return "owner_draw"
        if any(token in lowered for token in ("сем", "еда", "дом", "быт")):
            return "family_living"
        if any(token in lowered for token in ("sale", "income", "client", "РІС‹СЂСѓС‡", "Р°РІР°РЅСЃ")):
            return "sales_income"
        if any(token in lowered for token in ("part", "inventory", "С‚РѕРІР°СЂ", "Р·Р°РїС‡Р°СЃС‚", "СЃРєР»Р°Рґ")):
            return "inventory_parts"
        if any(token in lowered for token in ("salary", "team", "payroll", "Р·Р°СЂРїР»Р°С‚", "СЃРѕС‚СЂСѓРґ")):
            return "payroll_team"
        if any(token in lowered for token in ("rent", "utility", "Р°СЂРµРЅРґ", "РєРѕРјРјСѓРЅ")):
            return "rent_utilities"
        if any(token in lowered for token in ("taxi", "fuel", "delivery", "transport", "Р»РѕРіРёСЃС‚", "РґРѕСЃС‚Р°РІ")):
            return "logistics_transport"
        if any(token in lowered for token in ("ads", "marketing", "reklam", "С‚Р°СЂРіРµС‚")):
            return "marketing_growth"
        if any(token in lowered for token in ("tax", "fee", "РЅР°Р»РѕРі", "РєРѕРјРёСЃСЃ")):
            return "taxes_fees"
        if any(token in lowered for token in ("software", "tool", "subscription", "saas", "РїРѕРґРїРёСЃ")):
            return "tools_software"
        if any(token in lowered for token in ("owner", "withdraw", "draw", "СЃРµР±Рµ", "РґРёРІРёРґРµРЅРґ")):
            return "owner_draw"
        if any(token in lowered for token in ("family", "food", "home", "СЃРµРј", "РµРґР°", "РґРѕРј")):
            return "family_living"
        return "savings_debt"
