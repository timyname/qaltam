from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.app.models.enums import AccountType
from backend.app.models.profile import UserProfile
from backend.app.schemas.ingestion import TransactionDraft
from backend.app.schemas.onboarding import OnboardingReply
from backend.app.services.onboarding_service import OnboardingFlow
from backend.app.services.ocr_adapter import OcrAdapter
from backend.app.services.speech_adapter import SpeechAdapter
from backend.app.services.transaction_parser import TextTransactionParser


@dataclass(slots=True)
class IngestionResult:
    normalized_text: str
    transaction: TransactionDraft | None
    onboarding: OnboardingReply | None
    route: str


class IngestionService:
    def __init__(
        self,
        *,
        ocr_adapter: OcrAdapter | None = None,
        voice_adapter: SpeechAdapter | None = None,
        onboarding_flow: OnboardingFlow | None = None,
    ) -> None:
        self.ocr_adapter = ocr_adapter or OcrAdapter()
        self.voice_adapter = voice_adapter or SpeechAdapter()
        self.onboarding_flow = onboarding_flow or OnboardingFlow()

    def handle_text(self, *, profile: UserProfile, text: str) -> IngestionResult:
        if not profile.onboarding_completed:
            reply = self.onboarding_flow.advance(profile, text)
            return IngestionResult(
                normalized_text=text,
                transaction=None,
                onboarding=reply,
                route="onboarding",
            )

        draft = TextTransactionParser.parse(text)
        return IngestionResult(
            normalized_text=text,
            transaction=draft,
            onboarding=None,
            route="transaction" if draft else "fallback",
        )

    def handle_photo(self, *, profile: UserProfile, image_path: Path) -> IngestionResult:
        text = self.ocr_adapter.extract_text(image_path)
        return self.handle_text(profile=profile, text=text)

    def handle_voice(self, *, profile: UserProfile, audio_path: Path) -> IngestionResult:
        text = self.voice_adapter.transcribe(audio_path)
        return self.handle_text(profile=profile, text=text)

    def route_account_type(self, profile: UserProfile, draft: TransactionDraft | None) -> AccountType:
        if profile.client_mode.name == "PERSONAL":
            return AccountType.PERSONAL
        if draft and draft.transaction_type.value == "income":
            return AccountType.BUSINESS
        return AccountType.PERSONAL
