import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

from app.core.database import Base


class SpendingPlan(Base):
    """A workspace's daily spending plan: one allowance for every variable expense.

    Fixed costs are the recurring bills and planned costs are future-dated
    transactions; the projection already knows both. The plan only adds the
    daily allowance that every future day spends, the floor the balance must
    stay above, and which accounts hold the money it plans.
    """

    __tablename__ = "spending_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True, index=True
    )
    daily_allowance: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2))
    balance_floor: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), default=Decimal("0"), server_default="0"
    )
    # Account ids as strings. None plans every open account except loans.
    account_ids: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    horizon_months: Mapped[int] = mapped_column(Integer, default=12, server_default="12")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
