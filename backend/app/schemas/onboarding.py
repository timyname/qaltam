from decimal import Decimal

from pydantic import BaseModel, Field

from backend.app.models.enums import ClientMode, RiskLevel
from backend.app.schemas.account import AccountCreate
from backend.app.schemas.ingestion import AccountDraft
from backend.app.schemas.obligation import ObligationCreate


class UserProfileCreate(BaseModel):
    display_name: str
    client_mode: ClientMode = ClientMode.MIXED
    risk_level: RiskLevel = RiskLevel.MEDIUM
    preferred_language: str = "ru"
    communication_style: str | None = None
    owner_priority: str | None = None
    privacy_policy_note: str | None = "Local-only storage"


class GoalCreate(BaseModel):
    title: str
    target_amount: Decimal
    target_date: str | None = None
    note: str | None = None


class MemoryNoteCreate(BaseModel):
    kind: str
    title: str
    content: str
    importance: int = 1


class InitialOnboardingPayload(BaseModel):
    profile: UserProfileCreate
    accounts: list[AccountCreate]
    obligations: list[ObligationCreate] = []
    goals: list[GoalCreate] = []
    memory_notes: list[MemoryNoteCreate] = []


class OnboardingReply(BaseModel):
    message: str
    next_step: str
    next_prompt: str
    account_drafts: list[AccountDraft] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
