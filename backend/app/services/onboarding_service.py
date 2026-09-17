from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from backend.app.models.enums import ClientMode
from backend.app.models.profile import UserProfile
from backend.app.schemas.ingestion import AccountDraft
from backend.app.schemas.onboarding import OnboardingReply


@dataclass(slots=True)
class ParsedOnboardingData:
    accounts: list[AccountDraft]
    notes: list[str]


class OnboardingFlow:
    def start(self, profile: UserProfile) -> OnboardingReply:
        profile.onboarding_step = "awaiting_name"
        profile.onboarding_completed = False
        return OnboardingReply(
            message="\u041f\u0440\u0438\u0432\u0435\u0442. \u041d\u0430\u0447\u043d\u0435\u043c \u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u044e QALTAM.",
            next_step="awaiting_name",
            next_prompt="\u041a\u0430\u043a \u0432\u0430\u0441 \u043d\u0430\u0437\u044b\u0432\u0430\u0442\u044c?",
        )

    def advance(self, profile: UserProfile, message_text: str) -> OnboardingReply:
        step = profile.onboarding_step or "awaiting_name"
        normalized = message_text.strip()

        if step == "awaiting_name":
            profile.display_name = normalized
            profile.onboarding_step = "awaiting_mode"
            return OnboardingReply(
                message=f"\u041f\u0440\u0438\u043d\u044f\u0442\u043e, {profile.display_name}.",
                next_step="awaiting_mode",
                next_prompt="\u0412\u044b\u0431\u0435\u0440\u0438 \u0440\u0435\u0436\u0438\u043c: personal, business \u0438\u043b\u0438 mixed.",
            )

        if step == "awaiting_mode":
            profile.client_mode = self._parse_mode(normalized)
            profile.onboarding_step = "awaiting_accounts"
            return OnboardingReply(
                message=f"\u0420\u0435\u0436\u0438\u043c \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d: {profile.client_mode}.",
                next_step="awaiting_accounts",
                next_prompt="\u0422\u0435\u043f\u0435\u0440\u044c \u043f\u0440\u0438\u0448\u043b\u0438 \u0441\u0447\u0435\u0442\u0430 \u0438 \u043e\u0441\u0442\u0430\u0442\u043a\u0438 \u0432 \u0444\u043e\u0440\u043c\u0430\u0442\u0435 `Kaspi 1200000; Halyk 500000`.",
            )

        if step == "awaiting_accounts":
            parsed = self._parse_accounts(normalized)
            profile.onboarding_step = "awaiting_obligations"
            return OnboardingReply(
                message="\u0421\u0447\u0435\u0442\u0430 \u0437\u0430\u043f\u0438\u0441\u0430\u043d\u044b.",
                next_step="awaiting_obligations",
                next_prompt="\u0422\u0435\u043f\u0435\u0440\u044c \u043f\u0435\u0440\u0435\u0447\u0438\u0441\u043b\u0438 \u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u044b\u0435 \u043f\u043b\u0430\u0442\u0435\u0436\u0438 \u0438\u043b\u0438 \u0434\u043e\u043b\u0433\u0438.",
                account_drafts=parsed.accounts,
                notes=parsed.notes,
            )

        if step == "awaiting_obligations":
            profile.onboarding_step = "awaiting_goals"
            return OnboardingReply(
                message="\u041e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u0441\u0442\u0432\u0430 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u044b.",
                next_step="awaiting_goals",
                next_prompt="\u041a\u0430\u043a\u0438\u0435 \u0443 \u0442\u0435\u0431\u044f \u0433\u043b\u0430\u0432\u043d\u044b\u0435 \u0446\u0435\u043b\u0438 \u043d\u0430 \u0431\u043b\u0438\u0436\u0430\u0439\u0448\u0438\u0439 \u043f\u0435\u0440\u0438\u043e\u0434?",
                notes=[normalized],
            )

        profile.onboarding_completed = True
        profile.onboarding_step = "completed"
        return OnboardingReply(
            message="\u0420\u0435\u0433\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u044f \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0430.",
            next_step="completed",
            next_prompt="\u0413\u043e\u0442\u043e\u0432\u043e. \u041c\u043e\u0436\u0435\u0448\u044c \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u0442\u044c \u0442\u0440\u0430\u0442\u044b \u0438 \u043f\u043e\u0441\u0442\u0443\u043f\u043b\u0435\u043d\u0438\u044f.",
            notes=[normalized],
        )

    @staticmethod
    def _parse_mode(text: str) -> ClientMode:
        lowered = text.lower()
        if "business" in lowered:
            return ClientMode.BUSINESS
        if "personal" in lowered:
            return ClientMode.PERSONAL
        return ClientMode.MIXED

    @staticmethod
    def _parse_accounts(text: str) -> ParsedOnboardingData:
        chunks = [chunk.strip() for chunk in re.split(r"[;\n,]+", text) if chunk.strip()]
        account_drafts: list[AccountDraft] = []
        notes: list[str] = []
        for chunk in chunks:
            match = re.search(r"(?P<name>.*?)(?P<amount>\d[\d\s.,]*)$", chunk)
            if match:
                name = match.group("name").strip(" :-—")
                amount = Decimal(match.group("amount").replace(" ", "").replace(",", "."))
                if not name:
                    name = "account"
                account_drafts.append(AccountDraft(name=name, balance=amount, raw_text=chunk))
            else:
                account_drafts.append(AccountDraft(name=chunk, balance=Decimal("0"), raw_text=chunk))
            notes.append(chunk)
        return ParsedOnboardingData(accounts=account_drafts, notes=notes)
