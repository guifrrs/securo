import uuid
from datetime import date as _Date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SpendingPlanWrite(BaseModel):
    daily_allowance: Decimal = Field(ge=0)
    balance_floor: Decimal = Decimal("0")
    account_ids: Optional[list[uuid.UUID]] = None
    horizon_months: int = Field(default=12, ge=1, le=36)


class SpendingPlanRead(BaseModel):
    daily_allowance: Decimal
    balance_floor: Decimal
    account_ids: Optional[list[uuid.UUID]] = None
    horizon_months: int

    model_config = ConfigDict(from_attributes=True)


class SpendingPlanPoint(BaseModel):
    date: _Date
    balance: float


class SpendingPlanToday(BaseModel):
    allowance: float
    spent: float
    remaining: float


class SpendingPlanTimeline(BaseModel):
    currency: str
    daily_allowance: float
    balance_floor: float
    horizon_end: _Date
    #: Largest daily allowance that keeps every day through the horizon at or
    #: above the floor.
    safe_daily_allowance: float
    #: Last day the balance stays at or above the floor. None when today is
    #: already below it.
    covered_until: Optional[_Date] = None
    covered_through_horizon: bool
    today: SpendingPlanToday
    points: list[SpendingPlanPoint]
