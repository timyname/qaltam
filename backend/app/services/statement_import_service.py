from __future__ import annotations

from dataclasses import dataclass
import mimetypes
from pathlib import Path
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.localization import clarification_choice_label, normalize_language, text
from backend.app.models.profile import ImportedStatement, UserProfile
from backend.app.services.statement_clarification import (
    match_statement_clarification_choice,
    ordered_statement_clarification_choices,
    render_statement_clarification_choices,
)
from backend.app.services.chat_service import ChatService
from backend.app.services.memory_service import MemoryService
from backend.app.services.statement_classifier import (
    ClassifiedStatementItem,
    StatementClassifier,
    UnclearStatementItem,
)
from backend.app.services.statement_parser import ParsedStatement, StatementParser
from backend.app.services.transaction_service import TransactionService


@dataclass(slots=True)
class StatementImportResult:
    imported_statement_id: int
    parsed_count: int
    auto_count: int
    unclear_count: int
    summary_message: str
    prompt_message: str | None = None


@dataclass(slots=True)
class StatementStatusSnapshot:
    imported_statement_id: int
    source_name: str
    original_filename: str | None
    parse_status: str
    imported_at: str
    parsed_count: int | None
    auto_count: int | None
    unclear_count: int | None
    remaining_clarifications: int


@dataclass(slots=True)
class StatementHistorySnapshot:
    imported_statement_id: int
    source_name: str
    original_filename: str | None
    parse_status: str
    imported_at: str
    parsed_count: int | None
    auto_count: int | None
    unclear_count: int | None
    remaining_clarifications: int


@dataclass(slots=True)
class StatementDetailSnapshot:
    imported_statement_id: int
    source_name: str
    original_filename: str | None
    parse_status: str
    imported_at: str
    parsed_count: int | None
    auto_count: int | None
    unclear_count: int | None
    remaining_clarifications: int
    note: str | None
    storage_kind: str
    file_available: bool
    is_active: bool
    raw_line_count: int
    raw_preview: str
    raw_preview_truncated: bool


@dataclass(slots=True)
class StatementSourceSnapshot:
    filename: str
    media_type: str
    file_path: Path | None = None
    content: bytes | None = None


class ActiveStatementImportConflictError(RuntimeError):
    def __init__(self, *, statement_name: str, remaining_clarifications: int) -> None:
        self.statement_name = statement_name
        self.remaining_clarifications = remaining_clarifications
        super().__init__(
            f'Finish the active clarification for "{statement_name}" before importing a new statement. '
            f"Remaining clarifications: {remaining_clarifications}."
        )


class StatementImportService:
    RAW_PREVIEW_LINE_LIMIT = 12
    RAW_PREVIEW_CHAR_LIMIT = 1400

    def __init__(
        self,
        session: AsyncSession,
        *,
        parser: StatementParser | None = None,
        classifier: StatementClassifier | None = None,
    ) -> None:
        self.session = session
        self.chat = ChatService(session)
        self.memory = MemoryService(session)
        self.parser = parser or StatementParser(session)
        self.classifier = classifier or StatementClassifier(session)
        self.transactions = TransactionService(session)

    async def import_file(
        self,
        *,
        telegram_user_id: int,
        telegram_chat_id: int,
        file_path: Path,
        original_filename: str | None = None,
        language: str = "ru",
    ) -> StatementImportResult:
        profile = await self.chat.get_or_create_profile(telegram_user_id, telegram_chat_id)
        await self._ensure_import_slot_available(telegram_user_id)
        parsed_statement = await self.parser.parse_file(
            file_path,
            telegram_user_id=telegram_user_id,
            original_filename=original_filename,
            language=language,
        )
        return await self._process_import(profile, telegram_user_id, parsed_statement, language=language)

    async def import_text(
        self,
        *,
        telegram_user_id: int,
        telegram_chat_id: int,
        raw_text: str,
        language: str = "ru",
    ) -> StatementImportResult | None:
        if not StatementParser.looks_like_statement_text(raw_text):
            return None
        profile = await self.chat.get_or_create_profile(telegram_user_id, telegram_chat_id)
        await self._ensure_import_slot_available(telegram_user_id)
        parsed_statement = await self.parser.parse_text(
            raw_text,
            telegram_user_id=telegram_user_id,
            language=language,
        )
        return await self._process_import(profile, telegram_user_id, parsed_statement, language=language)

    async def process_clarification_text(
        self,
        *,
        telegram_user_id: int,
        telegram_chat_id: int,
        answer_text: str,
        language: str = "ru",
    ) -> str | None:
        pending = await self.memory.get_pending_statement(telegram_user_id)
        if not pending:
            return None
        profile = await self.chat.get_or_create_profile(telegram_user_id, telegram_chat_id)
        item = pending["items"][pending["current_index"]]
        matched_choice = match_statement_clarification_choice(answer_text, item, lang=language)
        if matched_choice:
            resolved = self.classifier.resolve_preselected_choice(
                item,
                account_type=matched_choice.account_type,
                life_sector=matched_choice.life_sector,
                rationale="Выбрано по текстовому быстрому ответу",
            )
        else:
            resolved = await self.classifier.resolve_manual_answer(profile, item, answer_text)
        await self._apply_clarification_resolution(telegram_user_id, pending, resolved)
        return self._build_clarification_response(pending, language=language)

    async def process_clarification_choice(
        self,
        *,
        telegram_user_id: int,
        telegram_chat_id: int,
        account_type: str,
        life_sector: str,
        language: str = "ru",
    ) -> str | None:
        pending = await self.memory.get_pending_statement(telegram_user_id)
        if not pending:
            return None
        await self.chat.get_or_create_profile(telegram_user_id, telegram_chat_id)
        item = pending["items"][pending["current_index"]]
        resolved = self.classifier.resolve_preselected_choice(
            item,
            account_type=account_type,
            life_sector=life_sector,
        )
        await self._apply_clarification_resolution(telegram_user_id, pending, resolved)
        return self._build_clarification_response(pending, language=language)

    async def get_pending_clarification(self, telegram_user_id: int) -> dict | None:
        return await self.memory.get_pending_statement(telegram_user_id)

    async def get_pending_prompt(self, telegram_user_id: int, *, language: str = "ru") -> str | None:
        pending = await self.get_pending_clarification(telegram_user_id)
        if not pending:
            return None
        return self._build_prompt(pending, language=language)

    async def has_pending_clarification(self, telegram_user_id: int) -> bool:
        return await self.memory.get_pending_statement(telegram_user_id) is not None

    async def get_latest_status(self, telegram_user_id: int) -> StatementStatusSnapshot | None:
        statement = await self._get_latest_imported_statement(telegram_user_id)
        if not statement:
            return None

        pending = await self.memory.get_pending_statement(telegram_user_id)
        metrics = self._parse_statement_metrics(statement.note)
        remaining_clarifications = 0
        if pending:
            total = len(pending.get("items") or [])
            current_index = int(pending.get("current_index", 0))
            remaining_clarifications = max(total - current_index, 0)

        imported_at = statement.imported_at.strftime("%Y-%m-%d %H:%M") if statement.imported_at else "unknown"
        return StatementStatusSnapshot(
            imported_statement_id=statement.id,
            source_name=statement.source_name,
            original_filename=statement.original_filename,
            parse_status=statement.parse_status,
            imported_at=imported_at,
            parsed_count=metrics.get("parsed"),
            auto_count=metrics.get("auto"),
            unclear_count=remaining_clarifications if pending else metrics.get("unclear"),
            remaining_clarifications=remaining_clarifications,
        )

    async def get_recent_history(self, telegram_user_id: int, *, limit: int = 6) -> list[StatementHistorySnapshot]:
        pending = await self.memory.get_pending_statement(telegram_user_id)
        result = await self.session.execute(
            select(ImportedStatement)
            .where(ImportedStatement.telegram_user_id == telegram_user_id)
            .order_by(ImportedStatement.imported_at.desc(), ImportedStatement.id.desc())
            .limit(limit)
        )
        statements = list(result.scalars().all())
        history: list[StatementHistorySnapshot] = []
        for statement in statements:
            metrics = self._parse_statement_metrics(statement.note)
            remaining_clarifications = 0
            unclear_count = metrics.get("unclear")
            if pending and int(pending.get("statement_id", 0)) == statement.id:
                total = len(pending.get("items") or [])
                current_index = int(pending.get("current_index", 0))
                remaining_clarifications = max(total - current_index, 0)
                unclear_count = remaining_clarifications
            history.append(
                StatementHistorySnapshot(
                    imported_statement_id=statement.id,
                    source_name=statement.source_name,
                    original_filename=statement.original_filename,
                    parse_status=statement.parse_status,
                    imported_at=statement.imported_at.strftime("%Y-%m-%d %H:%M") if statement.imported_at else "unknown",
                    parsed_count=metrics.get("parsed"),
                    auto_count=metrics.get("auto"),
                    unclear_count=unclear_count,
                    remaining_clarifications=remaining_clarifications,
                )
            )
        return history

    async def get_statement_detail(
        self,
        telegram_user_id: int,
        statement_id: int,
    ) -> StatementDetailSnapshot | None:
        statement = await self._get_imported_statement_for_user(telegram_user_id, statement_id)
        if not statement:
            return None

        pending = await self.memory.get_pending_statement(telegram_user_id)
        metrics = self._parse_statement_metrics(statement.note)
        is_active = bool(pending and int(pending.get("statement_id", 0)) == statement.id)
        remaining_clarifications = 0
        unclear_count = metrics.get("unclear")
        if is_active and pending:
            remaining_clarifications = self._remaining_clarifications(pending)
            unclear_count = remaining_clarifications

        raw_preview, raw_line_count, raw_preview_truncated = self._build_raw_preview(statement.raw_content or "")
        return StatementDetailSnapshot(
            imported_statement_id=statement.id,
            source_name=statement.source_name,
            original_filename=statement.original_filename,
            parse_status=statement.parse_status,
            imported_at=statement.imported_at.strftime("%Y-%m-%d %H:%M") if statement.imported_at else "unknown",
            parsed_count=metrics.get("parsed"),
            auto_count=metrics.get("auto"),
            unclear_count=unclear_count,
            remaining_clarifications=remaining_clarifications,
            note=statement.note,
            storage_kind=self._storage_kind(statement.file_path),
            file_available=self._statement_file_available(statement.file_path),
            is_active=is_active,
            raw_line_count=raw_line_count,
            raw_preview=raw_preview,
            raw_preview_truncated=raw_preview_truncated,
        )

    async def get_statement_source(
        self,
        telegram_user_id: int,
        statement_id: int,
    ) -> StatementSourceSnapshot | None:
        statement = await self._get_imported_statement_for_user(telegram_user_id, statement_id)
        if not statement:
            return None

        filename = self._statement_source_filename(statement)
        if self._statement_file_available(statement.file_path):
            file_path = Path(statement.file_path)
            return StatementSourceSnapshot(
                filename=filename,
                media_type=self._statement_media_type(filename),
                file_path=file_path,
            )

        raw_content = statement.raw_content or ""
        if raw_content.strip():
            fallback_filename = self._statement_source_filename(statement, prefer_raw_text=True)
            return StatementSourceSnapshot(
                filename=fallback_filename,
                media_type="text/plain; charset=utf-8",
                content=raw_content.encode("utf-8"),
            )

        return None

    async def _process_import(
        self,
        profile: UserProfile,
        telegram_user_id: int,
        parsed_statement: ParsedStatement,
        *,
        language: str = "ru",
    ) -> StatementImportResult:
        classification = await self.classifier.classify_entries(
            profile,
            parsed_statement.entries,
            telegram_user_id=telegram_user_id,
        )
        auto_count = 0
        for item in classification.auto_categorized:
            await self._persist_transaction(parsed_statement.imported_statement.id, telegram_user_id, item)
            auto_count += 1

        learned_rules = await self.memory.get_clarification_rules(telegram_user_id)
        unclear_payload = {
            "statement_id": parsed_statement.imported_statement.id,
            "parsed_count": len(parsed_statement.entries),
            "auto_count": auto_count,
            "current_index": 0,
            "items": [
                self._serialize_unclear_item(item, learned_rules, language=language)
                for item in classification.unclear_items
            ],
        }
        if classification.unclear_items:
            await self.memory.save_pending_statement(telegram_user_id, unclear_payload)
            parsed_statement.imported_statement.parse_status = "clarification_required"
        else:
            await self.memory.clear_pending_statement(telegram_user_id)
            parsed_statement.imported_statement.parse_status = "completed"

        parsed_statement.imported_statement.note = (
            f"parsed={len(parsed_statement.entries)} auto={auto_count} unclear={len(classification.unclear_items)}"
        )
        await self.session.flush()

        prompt_message = self._build_prompt(unclear_payload, language=language) if classification.unclear_items else None
        return StatementImportResult(
            imported_statement_id=parsed_statement.imported_statement.id,
            parsed_count=len(parsed_statement.entries),
            auto_count=auto_count,
            unclear_count=len(classification.unclear_items),
            summary_message=text(
                "statement_processing_summary",
                language,
                parsed_count=len(parsed_statement.entries),
                auto_count=auto_count,
                unclear_count=len(classification.unclear_items),
            ),
            prompt_message=prompt_message,
        )

    async def _apply_clarification_resolution(
        self,
        telegram_user_id: int,
        pending: dict,
        resolved: ClassifiedStatementItem,
    ) -> None:
        await self._persist_transaction(int(pending["statement_id"]), telegram_user_id, resolved)
        await self.memory.save_clarification_rule(
            telegram_user_id,
            match_key=resolved.match_key,
            account_type=resolved.account_type.value,
            life_sector=resolved.life_sector,
            explanation=resolved.rationale,
        )

        pending["current_index"] += 1
        if pending["current_index"] >= len(pending["items"]):
            await self.memory.clear_pending_statement(telegram_user_id)
            statement = await self._get_imported_statement(int(pending["statement_id"]))
            if statement:
                statement.parse_status = "completed"
                statement.note = (
                    f"parsed={pending['parsed_count']} auto={pending['auto_count']} unclear=0 resolved=all"
                )
            await self.session.flush()
            return

        await self.memory.save_pending_statement(telegram_user_id, pending)
        await self.session.flush()

    async def _persist_transaction(
        self,
        statement_id: int,
        telegram_user_id: int,
        item: ClassifiedStatementItem,
    ) -> None:
        await self.transactions.create_transaction(
            amount=item.amount,
            category=item.life_sector,
            transaction_type=item.transaction_type,
            account_type_hint=item.account_type,
            note=self._statement_note(statement_id, item),
            created_at=self._to_datetime(item.statement_date),
            telegram_user_id=telegram_user_id,
        )

    async def _get_imported_statement(self, statement_id: int) -> ImportedStatement | None:
        result = await self.session.execute(select(ImportedStatement).where(ImportedStatement.id == statement_id))
        return result.scalars().first()

    async def _get_imported_statement_for_user(
        self,
        telegram_user_id: int,
        statement_id: int,
    ) -> ImportedStatement | None:
        result = await self.session.execute(
            select(ImportedStatement).where(
                ImportedStatement.id == statement_id,
                ImportedStatement.telegram_user_id == telegram_user_id,
            )
        )
        return result.scalars().first()

    async def _get_latest_imported_statement(self, telegram_user_id: int) -> ImportedStatement | None:
        result = await self.session.execute(
            select(ImportedStatement)
            .where(ImportedStatement.telegram_user_id == telegram_user_id)
            .order_by(ImportedStatement.imported_at.desc(), ImportedStatement.id.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def _ensure_import_slot_available(self, telegram_user_id: int) -> None:
        pending = await self.memory.get_pending_statement(telegram_user_id)
        if not pending:
            return

        remaining_clarifications = self._remaining_clarifications(pending)
        if remaining_clarifications <= 0:
            return

        statement = await self._get_imported_statement(int(pending.get("statement_id", 0)))
        statement_name = self._statement_name(statement, pending)
        raise ActiveStatementImportConflictError(
            statement_name=statement_name,
            remaining_clarifications=remaining_clarifications,
        )

    @staticmethod
    def _build_prompt(pending: dict, *, language: str = "ru") -> str:
        current_index = int(pending["current_index"])
        item = pending["items"][current_index]
        ordinal = current_index + 1
        total = len(pending["items"])
        quick_choices = render_statement_clarification_choices(item, lang=language)
        return "\n".join(
            part
            for part in [
                text("statement_prompt_intro", language, auto_count=pending["auto_count"], ordinal=ordinal, total=total),
                StatementImportService._format_pending_item(item, language=language),
                StatementImportService._format_pending_description(item, language=language),
                text(
                    "statement_reason_label",
                    language,
                    reason=StatementImportService._localized_reason(item["reason"], language),
                ),
                StatementImportService._format_pending_rules(item, language=language),
                StatementImportService._format_pending_suggestion(item, language=language),
                StatementImportService._format_primary_choice_hint(item, language=language),
                StatementImportService._format_same_as_before_hint(item, language=language),
                quick_choices,
                text("statement_prompt_reply_example", language),
            ]
            if part
        )

    @staticmethod
    def _build_clarification_response(pending: dict, *, language: str = "ru") -> str:
        current_index = int(pending["current_index"])
        total = len(pending["items"])
        if current_index >= total:
            return text("statement_completion_saved", language)
        item = pending["items"][current_index]
        ordinal = current_index + 1
        quick_choices = render_statement_clarification_choices(item, lang=language)
        return "\n".join(
            part
            for part in [
                text("statement_next_clarification", language, ordinal=ordinal, total=total),
                StatementImportService._format_pending_item(item, language=language),
                StatementImportService._format_pending_description(item, language=language),
                text(
                    "statement_reason_label",
                    language,
                    reason=StatementImportService._localized_reason(item["reason"], language),
                ),
                StatementImportService._format_pending_rules(item, language=language),
                StatementImportService._format_pending_suggestion(item, language=language),
                StatementImportService._format_primary_choice_hint(item, language=language),
                StatementImportService._format_same_as_before_hint(item, language=language),
                quick_choices,
                text("statement_prompt_reply_tap", language),
            ]
            if part
        )

    @staticmethod
    def _statement_note(statement_id: int, item: ClassifiedStatementItem) -> str:
        note = f"[stmt:{statement_id}] {item.counterparty} | {item.description} | {item.rationale}"
        return note[:255]

    @staticmethod
    def _to_datetime(value):
        from datetime import datetime, time, timezone

        return datetime.combine(value, time.min, tzinfo=timezone.utc)

    @staticmethod
    def _format_pending_item(item: dict, *, language: str = "ru") -> str:
        return text(
            "statement_item_line",
            language,
            transaction_type=text(f"statement_transaction_{item['transaction_type']}", language),
            amount=item["amount"],
            counterparty=item["counterparty"],
            statement_date=item["statement_date"],
        )

    @staticmethod
    def _format_pending_description(item: dict, *, language: str = "ru") -> str:
        description = str(item.get("description") or "").strip()
        counterparty = str(item.get("counterparty") or "").strip()
        if not description or description.casefold() == counterparty.casefold():
            return ""
        return text("statement_description_label", language, description=description)

    @staticmethod
    def _format_pending_suggestion(item: dict, *, language: str = "ru") -> str:
        suggested_account_type = item.get("suggested_account_type")
        suggested_life_sector = item.get("suggested_life_sector")
        if not suggested_account_type or not suggested_life_sector:
            return ""
        return text(
            "statement_suggested_quick_choice",
            language,
            choice=clarification_choice_label(str(suggested_account_type), str(suggested_life_sector), language),
        )

    @staticmethod
    def _format_pending_rules(item: dict, *, language: str = "ru") -> str:
        matched_rules = item.get("matched_rules") or []
        if not matched_rules:
            return ""

        lines = [
            text("statement_matched_rules_intro", language),
            *[
                text(
                    "statement_matched_rule_line",
                    language,
                    choice=clarification_choice_label(
                        str(rule.get("account_type") or "personal"),
                        str(rule.get("life_sector") or "family_living"),
                        language,
                    ),
                    explanation=StatementImportService._localized_explanation(
                        str(rule.get("explanation") or ""),
                        language,
                    ),
                    )
                for rule in matched_rules
            ],
        ]
        return "\n".join(lines)

    @staticmethod
    def _format_primary_choice_hint(item: dict, *, language: str = "ru") -> str:
        if not item.get("suggested_account_type") and not item.get("matched_rules"):
            return ""

        choices = ordered_statement_clarification_choices(item, lang=language)
        if not choices:
            return ""

        first_choice = choices[0]
        if not first_choice.is_suggested and not first_choice.is_learned:
            return ""

        return text("statement_primary_choice_hint", language, choice=first_choice.label)

    @staticmethod
    def _format_same_as_before_hint(item: dict, *, language: str = "ru") -> str:
        matched_rules = item.get("matched_rules") or []
        if not matched_rules:
            return ""
        return text("statement_same_as_before_hint", language)

    @staticmethod
    def _serialize_unclear_item(item: UnclearStatementItem, learned_rules: list[dict], *, language: str = "ru") -> dict:
        matched_rules = StatementClassifier.find_related_rules(
            item.counterparty,
            item.description,
            learned_rules,
        )
        return {
            "index": item.index,
            "statement_date": item.statement_date.isoformat(),
            "amount": str(item.amount),
            "transaction_type": item.transaction_type.value,
            "counterparty": item.counterparty,
            "description": item.description,
            "reason": StatementImportService._localized_reason(item.reason, language),
            "suggested_account_type": item.suggested_account_type.value if item.suggested_account_type else None,
            "suggested_life_sector": item.suggested_life_sector,
            "matched_rules": [
                {
                    "match_key": str(rule.get("match_key") or ""),
                    "account_type": str(rule.get("account_type") or ""),
                    "life_sector": str(rule.get("life_sector") or ""),
                    "explanation": StatementImportService._localized_explanation(
                        str(rule.get("explanation") or ""),
                        language,
                    ),
                }
                for rule in matched_rules
            ],
        }

    @staticmethod
    def _localized_reason(reason: str, language: str) -> str:
        normalized_language = normalize_language(language, default="ru")
        if normalized_language != "ru":
            return reason

        translations = {
            "Ambiguous P2P transfer to a person.": "Неоднозначный P2P-перевод физическому лицу.",
            "Bank statement header row.": "Шапка банковской выписки.",
            "Statement header row.": "Шапка банковской выписки.",
            "Statement header.": "Шапка банковской выписки.",
            "Need clarification.": "Нужно уточнение.",
            "Model did not classify the item confidently.": "Модель не смогла уверенно классифицировать операцию.",
            "DeepSeek is unavailable, clarification required.": "Нужна ручная проверка: сервис DeepSeek сейчас недоступен.",
            "Not a real transaction": "Не является реальной транзакцией",
        }
        return translations.get(reason, reason)

    @staticmethod
    def _localized_explanation(explanation: str, language: str) -> str:
        normalized_language = normalize_language(language, default="ru")
        if normalized_language != "ru":
            return explanation

        replacements = {
            "Memory rule:": "Правило из памяти:",
            "Resolved from quick button": "Выбрано через быструю кнопку",
            "Resolved from typed quick choice": "Выбрано по текстовому быстрому ответу",
            "Resolved from user clarification.": "Категория определена по ответу пользователя.",
            "DeepSeek classified the transaction.": "Транзакция классифицирована автоматически.",
        }
        localized = explanation
        for source, target in replacements.items():
            localized = localized.replace(source, target)
        return localized

    @staticmethod
    def _parse_statement_metrics(note: str | None) -> dict[str, int]:
        if not note:
            return {}
        metrics: dict[str, int] = {}
        for key, value in re.findall(r"([a-z_]+)=(\d+)", note):
            metrics[key] = int(value)
        return metrics

    @staticmethod
    def _remaining_clarifications(pending: dict) -> int:
        total = len(pending.get("items") or [])
        current_index = int(pending.get("current_index", 0))
        return max(total - current_index, 0)

    @staticmethod
    def _statement_name(statement: ImportedStatement | None, pending: dict) -> str:
        if statement:
            return statement.original_filename or statement.source_name
        statement_id = pending.get("statement_id")
        return f"statement #{statement_id}" if statement_id else "current statement"

    @classmethod
    def _build_raw_preview(cls, raw_content: str) -> tuple[str, int, bool]:
        normalized = raw_content.strip()
        if not normalized:
            return "", 0, False

        lines = [line.rstrip() for line in normalized.splitlines()]
        preview_lines = lines[: cls.RAW_PREVIEW_LINE_LIMIT]
        preview = "\n".join(preview_lines)
        truncated = len(lines) > cls.RAW_PREVIEW_LINE_LIMIT
        if len(preview) > cls.RAW_PREVIEW_CHAR_LIMIT:
            preview = preview[: cls.RAW_PREVIEW_CHAR_LIMIT].rstrip()
            truncated = True
        return preview, len(lines), truncated

    @staticmethod
    def _storage_kind(file_path: str) -> str:
        return "virtual_text" if file_path.startswith("telegram://") else "local_file"

    @staticmethod
    def _statement_file_available(file_path: str) -> bool:
        if file_path.startswith("telegram://"):
            return False
        return Path(file_path).exists()

    @staticmethod
    def _statement_media_type(filename: str) -> str:
        media_type, _ = mimetypes.guess_type(filename)
        return media_type or "application/octet-stream"

    @classmethod
    def _statement_source_filename(
        cls,
        statement: ImportedStatement,
        *,
        prefer_raw_text: bool = False,
    ) -> str:
        candidate = statement.original_filename or Path(statement.file_path).name or statement.source_name
        filename = Path(candidate).name or f"statement_{statement.id}"
        if prefer_raw_text or cls._storage_kind(statement.file_path) == "virtual_text":
            stem = Path(filename).stem or filename
            return f"{stem}.txt"
        return filename
