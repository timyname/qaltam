from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum as SqlEnum
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models.enums import ClientMode, RiskLevel


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int | None] = mapped_column(nullable=True, unique=True, index=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    client_mode: Mapped[ClientMode] = mapped_column(SqlEnum(ClientMode), default=ClientMode.MIXED)
    risk_level: Mapped[RiskLevel] = mapped_column(SqlEnum(RiskLevel), default=RiskLevel.MEDIUM)
    preferred_language: Mapped[str] = mapped_column(String(12), default="ru")
    communication_style: Mapped[str | None] = mapped_column(String(120), nullable=True)
    owner_priority: Mapped[str | None] = mapped_column(String(120), nullable=True)
    privacy_policy_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    onboarding_step: Mapped[str] = mapped_column(String(40), default="awaiting_name", index=True)
    onboarding_completed: Mapped[bool] = mapped_column(default=False, index=True)
    memory_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class MemoryNote(Base):
    __tablename__ = "memory_notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text)
    importance: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None), index=True)


class ImportedStatement(Base):
    __tablename__ = "imported_statements"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(120))
    file_path: Mapped[str] = mapped_column(String(255), unique=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        index=True,
    )
    parse_status: Mapped[str] = mapped_column(String(30), default="pending")
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
