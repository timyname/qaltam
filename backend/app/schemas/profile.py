from pydantic import BaseModel, field_validator

from backend.app.localization import normalize_language


class ProfilePreferencesUpdateRequest(BaseModel):
    telegram_user_id: int
    preferred_language: str

    @field_validator("preferred_language")
    @classmethod
    def normalize_preferred_language(cls, value: str) -> str:
        return normalize_language(value, default="ru")


class ProfilePreferencesResponse(BaseModel):
    telegram_user_id: int
    preferred_language: str
