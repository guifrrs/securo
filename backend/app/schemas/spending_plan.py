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


class SimulatedPurchase(BaseModel):
    description: Optional[str] = None
    amount: Decimal = Field(gt=0)
    installments: int = Field(default=1, ge=1, le=120)
    first_date: _Date


class SpendingPlanSimulation(BaseModel):
    daily_allowance: Optional[Decimal] = Field(default=None, ge=0)
    purchases: list[SimulatedPurchase] = Field(min_length=1, max_length=20)


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
    #: How much the balance grows per day on average through the horizon when
    #: nothing beyond bills and planned rows is spent: what is left to spend.
    average_daily_surplus: float
    #: Last day the balance stays at or above the floor. None when today is
    #: already below it.
    covered_until: Optional[_Date] = None
    covered_through_horizon: bool
    today: SpendingPlanToday
    points: list[SpendingPlanPoint]
