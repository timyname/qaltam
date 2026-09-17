from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.localization import normalize_language, text as localized_text
from backend.app.models.enums import AccountType, ClientMode, RiskLevel, TransactionType
from backend.app.models.profile import UserProfile
from backend.app.schemas.onboarding import OnboardingReply
from backend.app.services.account_service import AccountService
from backend.app.services.ingestion import IngestionService
from backend.app.services.llm_transaction_classifier import LlmTransactionClassifier
from backend.app.services.memory_service import MemoryService
from backend.app.services.onboarding_service import OnboardingFlow
from backend.app.services.receipt_service import ReceiptService
from backend.app.services.transaction_service import TransactionService


class ChatService:
    def __init__(
        self,
        session: AsyncSession,
        classifier: LlmTransactionClassifier | None = None,
        receipt_service: ReceiptService | None = None,
    ) -> None:
        self.session = session
        self.onboarding = OnboardingFlow()
        self.ingestion = IngestionService(onboarding_flow=self.onboarding)
        self.transactions = TransactionService(session)
        self.accounts = AccountService(session)
        self.memory = MemoryService(session)
        self.classifier = classifier or LlmTransactionClassifier()
        self.receipts = receipt_service or ReceiptService(session)

    async def get_or_create_profile(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
        *,
        fallback_language_code: str | None = None,
    ) -> UserProfile:
        from sqlalchemy import select

        result = await self.session.execute(
            select(UserProfile).where(UserProfile.telegram_user_id == telegram_user_id)
        )
        profile = result.scalars().first()
        if profile:
            profile.telegram_chat_id = telegram_chat_id
            return profile

        profile = UserProfile(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            display_name="",
            client_mode=ClientMode.MIXED,
            risk_level=RiskLevel.MEDIUM,
            preferred_language=normalize_language(fallback_language_code, default="ru"),
            communication_style=None,
            owner_priority=None,
            privacy_policy_note="local only",
            onboarding_step="awaiting_name",
            onboarding_completed=False,
        )
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def start(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
        *,
        fallback_language_code: str | None = None,
    ) -> str:
        profile = await self.get_or_create_profile(
            telegram_user_id,
            telegram_chat_id,
            fallback_language_code=fallback_language_code,
        )
        reply = self.onboarding.start(profile)
        await self.session.flush()
        return reply.message + "\n" + reply.next_prompt

    async def process_text(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
        text: str,
        *,
        fallback_language_code: str | None = None,
    ) -> str:
        profile = await self.get_or_create_profile(
            telegram_user_id,
            telegram_chat_id,
            fallback_language_code=fallback_language_code,
        )
        lang = profile.preferred_language

        if not profile.onboarding_completed:
            reply = self.onboarding.advance(profile, text)
            await self._persist_onboarding_artifacts(profile, reply)
            await self.session.commit()
            return reply.message + "\n" + reply.next_prompt

        outcome = self.ingestion.handle_text(profile=profile, text=text)
        if outcome.transaction:
            account_type = self._infer_account_type(profile, outcome.transaction.transaction_type.value)
            transaction = await self.transactions.create_from_draft(
                outcome.transaction,
                account_type,
                telegram_user_id=telegram_user_id,
            )
            await self.session.commit()
            return localized_text("chat_logged", lang, category=transaction.category, amount=transaction.amount)

        llm_draft = await self.classifier.classify_text(text)
        if llm_draft:
            account_type = self._infer_account_type(profile, llm_draft.transaction_type.value)
            transaction = await self.transactions.create_from_draft(
                llm_draft,
                account_type,
                telegram_user_id=telegram_user_id,
            )
            await self.session.commit()
            return localized_text("chat_logged", lang, category=transaction.category, amount=transaction.amount)

        await self.memory.add_note(kind="message", title="Unhandled message", content=text, importance=1)
        await self.session.commit()
        return localized_text("chat_need_clarification", lang)

    async def process_photo(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
        image_path,
        *,
        fallback_language_code: str | None = None,
    ) -> str:
        receipt_reply = await self.process_receipt_upload(
            telegram_user_id,
            telegram_chat_id,
            image_path,
            fallback_language_code=fallback_language_code,
        )
        if receipt_reply:
            return receipt_reply

        profile = await self.get_or_create_profile(
            telegram_user_id,
            telegram_chat_id,
            fallback_language_code=fallback_language_code,
        )
        lang = profile.preferred_language
        outcome = self.ingestion.handle_photo(profile=profile, image_path=image_path)
        if outcome.onboarding:
            await self._persist_onboarding_artifacts(profile, outcome.onboarding)
            await self.session.commit()
            return outcome.onboarding.message + "\n" + outcome.onboarding.next_prompt
        if outcome.transaction:
            account_type = self._infer_account_type(profile, outcome.transaction.transaction_type.value)
            transaction = await self.transactions.create_from_draft(
                outcome.transaction,
                account_type,
                telegram_user_id=telegram_user_id,
            )
            await self.session.commit()
            return localized_text("photo_recognized", lang, category=transaction.category, amount=transaction.amount)
        llm_draft = await self.classifier.classify_text(outcome.normalized_text)
        if llm_draft:
            account_type = self._infer_account_type(profile, llm_draft.transaction_type.value)
            transaction = await self.transactions.create_from_draft(
                llm_draft,
                account_type,
                telegram_user_id=telegram_user_id,
            )
            await self.session.commit()
            return localized_text("photo_recognized", lang, category=transaction.category, amount=transaction.amount)
        await self.memory.add_note(
            kind="receipt",
            title="Photo receipt",
            content="\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u0442\u044c \u0442\u0435\u043a\u0441\u0442.",
            importance=1,
        )
        await self.session.commit()
        return localized_text("photo_not_recognized", lang)

    async def process_receipt_upload(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
        image_path,
        *,
        fallback_language_code: str | None = None,
    ) -> str | None:
        profile = await self.get_or_create_profile(
            telegram_user_id,
            telegram_chat_id,
            fallback_language_code=fallback_language_code,
        )
        parsed_receipt = await self.receipts.ingest_photo(telegram_user_id=telegram_user_id, image_path=image_path)
        if not parsed_receipt:
            return None
        transaction = await self._create_transaction_from_receipt(profile, parsed_receipt)
        await self.session.commit()
        return self._receipt_saved_message(parsed_receipt, transaction.amount, profile.preferred_language)

    async def process_voice(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
        audio_path,
        *,
        fallback_language_code: str | None = None,
    ) -> str:
        profile = await self.get_or_create_profile(
            telegram_user_id,
            telegram_chat_id,
            fallback_language_code=fallback_language_code,
        )
        lang = profile.preferred_language
        outcome = self.ingestion.handle_voice(profile=profile, audio_path=audio_path)
        if outcome.onboarding:
            await self._persist_onboarding_artifacts(profile, outcome.onboarding)
            await self.session.commit()
            return outcome.onboarding.message + "\n" + outcome.onboarding.next_prompt
        if outcome.transaction:
            account_type = self._infer_account_type(profile, outcome.transaction.transaction_type.value)
            transaction = await self.transactions.create_from_draft(
                outcome.transaction,
                account_type,
                telegram_user_id=telegram_user_id,
            )
            await self.session.commit()
            return localized_text("voice_logged", lang, category=transaction.category, amount=transaction.amount)
        llm_draft = await self.classifier.classify_text(outcome.normalized_text)
        if llm_draft:
            account_type = self._infer_account_type(profile, llm_draft.transaction_type.value)
            transaction = await self.transactions.create_from_draft(
                llm_draft,
                account_type,
                telegram_user_id=telegram_user_id,
            )
            await self.session.commit()
            return localized_text("voice_logged", lang, category=transaction.category, amount=transaction.amount)
        await self.memory.add_note(
            kind="voice",
            title="Voice note",
            content="\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u0442\u044c \u0440\u0435\u0447\u044c.",
            importance=1,
        )
        await self.session.commit()
        return localized_text("voice_not_recognized", lang)

    async def _persist_onboarding_artifacts(self, profile: UserProfile, reply: OnboardingReply) -> None:
        if reply.account_drafts:
            for draft in reply.account_drafts:
                account_type = self._infer_account_type(profile, draft.name)
                await self.accounts.create_account_from_draft(
                    draft,
                    account_type,
                    telegram_user_id=profile.telegram_user_id,
                )
        for note in reply.notes:
            await self.memory.add_note(kind="onboarding", title="Onboarding reply", content=note, importance=1)
        if reply.next_step == "completed":
            await self.memory.attach_summary_to_profile(profile)

    @staticmethod
    def _infer_account_type(profile: UserProfile, seed: str) -> AccountType:
        if profile.client_mode == ClientMode.PERSONAL:
            return AccountType.PERSONAL
        if profile.client_mode == ClientMode.BUSINESS:
            return AccountType.BUSINESS
        lowered = seed.lower()
        if any(token in lowered for token in ("biz", "business", "corp", "company")):
            return AccountType.BUSINESS
        return AccountType.PERSONAL

    @staticmethod
    def _receipt_transaction_type(category: str) -> TransactionType:
        return TransactionType.EXPENSE

    @staticmethod
    def _receipt_note(receipt) -> str:
        merchant = receipt.merchant_name or "unknown_merchant"
        top_items = ", ".join(item.sku_name for item in receipt.items[:4])
        return f"receipt:{merchant}; items:{top_items}"

    async def _create_transaction_from_receipt(self, profile: UserProfile, parsed_receipt):
        category = self.receipts.dominant_category(parsed_receipt)
        account_type = self._infer_account_type(profile, category)
        return await self.transactions.create_transaction(
            amount=parsed_receipt.total_amount,
            category=category,
            transaction_type=self._receipt_transaction_type(category),
            account_type_hint=account_type,
            note=self._receipt_note(parsed_receipt),
            telegram_user_id=profile.telegram_user_id,
        )

    @staticmethod
    def _receipt_saved_message(parsed_receipt, amount, lang: str) -> str:
        top_items = ", ".join(item.sku_name for item in parsed_receipt.items[:3])
        merchant = parsed_receipt.merchant_name or "Receipt"
        return localized_text(
            "receipt_saved",
            lang,
            merchant=merchant,
            amount=amount,
            sku_count=len(parsed_receipt.items),
            top_items=top_items,
        )
