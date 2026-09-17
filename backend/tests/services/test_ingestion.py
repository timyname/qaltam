from decimal import Decimal
from pathlib import Path

from backend.app.models.enums import ClientMode, TransactionType
from backend.app.models.profile import UserProfile
from backend.app.services.ingestion import IngestionService, OnboardingFlow, TextTransactionParser


class FakeOcrAdapter:
    def __init__(self, text: str):
        self.text = text

    def extract_text(self, _: Path) -> str:
        return self.text


class FakeVoiceAdapter:
    def __init__(self, text: str):
        self.text = text

    def transcribe(self, _: Path) -> str:
        return self.text


def test_text_parser_reads_amount_category_and_defaults_to_expense():
    draft = TextTransactionParser.parse("17000 kassa")

    assert draft.amount == Decimal("17000")
    assert draft.category == "kassa"
    assert draft.transaction_type == TransactionType.EXPENSE


def test_text_parser_reads_income_markers():
    draft = TextTransactionParser.parse("250000 \u043f\u043e\u0441\u0442\u0443\u043f\u043b\u0435\u043d\u0438\u0435 client")

    assert draft.amount == Decimal("250000")
    assert draft.transaction_type == TransactionType.INCOME
    assert draft.category == "client"


def test_ingestion_routes_photo_and_voice_payloads_to_same_parser():
    service = IngestionService(
        ocr_adapter=FakeOcrAdapter("12000 coffee"),
        voice_adapter=FakeVoiceAdapter("5000 taxi"),
    )
    profile = UserProfile(
        telegram_user_id=1,
        telegram_chat_id=1,
        display_name="Ali",
        client_mode=ClientMode.MIXED,
        risk_level="medium",
        preferred_language="ru",
        communication_style="short",
        owner_priority="cash",
        privacy_policy_note="local only",
        onboarding_step="completed",
        onboarding_completed=True,
    )

    photo_result = service.handle_photo(profile=profile, image_path=Path("receipt.jpg"))
    voice_result = service.handle_voice(profile=profile, audio_path=Path("voice.ogg"))

    assert photo_result.normalized_text == "12000 coffee"
    assert photo_result.transaction.amount == Decimal("12000")
    assert voice_result.normalized_text == "5000 taxi"
    assert voice_result.transaction.amount == Decimal("5000")


def test_onboarding_flow_advances_registration_steps():
    profile = UserProfile(
        telegram_user_id=1,
        telegram_chat_id=1,
        display_name="",
        client_mode=ClientMode.MIXED,
        risk_level="medium",
        preferred_language="ru",
        communication_style=None,
        owner_priority=None,
        privacy_policy_note="local only",
        onboarding_step="awaiting_name",
        onboarding_completed=False,
    )
    flow = OnboardingFlow()

    first = flow.start(profile)
    second = flow.advance(profile, "\u0410\u043b\u0438\u0448\u0435\u0440")
    third = flow.advance(profile, "business")
    fourth = flow.advance(profile, "Kaspi 1200000; Halyk 500000")
    fifth = flow.advance(profile, "\u0430\u0440\u0435\u043d\u0434\u0430 250000")
    sixth = flow.advance(profile, "\u0446\u0435\u043b\u044c: \u0437\u0430\u043a\u0440\u044b\u0442\u044c \u043a\u0430\u0441\u0441\u043e\u0432\u044b\u0439 \u0440\u0430\u0437\u0440\u044b\u0432")

    assert "QALTAM" in first.message
    assert "\u041a\u0430\u043a \u0432\u0430\u0441 \u043d\u0430\u0437\u044b\u0432\u0430\u0442\u044c" in first.next_prompt
    assert profile.display_name == "\u0410\u043b\u0438\u0448\u0435\u0440"
    assert profile.client_mode == ClientMode.BUSINESS
    assert "\u0440\u0435\u0436\u0438\u043c" in second.next_prompt
    assert "\u0441\u0447\u0435\u0442\u0430 \u0438 \u043e\u0441\u0442\u0430\u0442\u043a\u0438" in third.next_prompt
    assert "\u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u044b\u0435 \u043f\u043b\u0430\u0442\u0435\u0436\u0438" in fourth.next_prompt
    assert "\u0446\u0435\u043b\u0438" in fifth.next_prompt
    assert profile.onboarding_completed is True
    assert sixth.next_step == "completed"
