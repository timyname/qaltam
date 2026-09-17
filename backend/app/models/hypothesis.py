from decimal import Decimal

from sqlalchemy import Enum as SqlEnum
from sqlalchemy import Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models.enums import HypothesisStatus, RiskLevel, RoleTag


class Hypothesis(Base):
    __tablename__ = "hypotheses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(150), index=True)
    role_perspective: Mapped[RoleTag] = mapped_column(SqlEnum(RoleTag), index=True)
    required_investment: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    time_lag_days: Mapped[int] = mapped_column(Integer)
    expected_roi: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    risk_level: Mapped[RiskLevel] = mapped_column(SqlEnum(RiskLevel), default=RiskLevel.MEDIUM)
    status: Mapped[HypothesisStatus] = mapped_column(SqlEnum(HypothesisStatus), default=HypothesisStatus.DRAFT)
