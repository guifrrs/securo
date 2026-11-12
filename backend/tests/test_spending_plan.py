import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.app_clock import app_today
from app.models.account import Account
from app.models.category import Category
from app.models.recurring_transaction import RecurringTransaction
from app.models.transaction import Transaction
from app.schemas.spending_plan import SpendingPlanWrite
from app.services.balance_projection import (
    ProjectionBase,
    covered_until,
    safe_daily_allowance,
    walk,
)
from app.services.spending_plan_service import get_timeline, save_plan
from app.services.transaction_calendar_service import get_transaction_calendar

TODAY = date(2027, 3, 10)


def _base(seed: float, deltas: dict[int, float], start: date = TODAY, days: int = 5) -> ProjectionBase:
    return ProjectionBase(
        start=start,
        end=start + timedelta(days=days),
        seed=seed,
        deltas={TODAY + timedelta(days=offset): delta for offset, delta in deltas.items()},
        forecast_rows=[],
        recurring_items=[],
    )


def test_walk_spends_what_is_left_of_today_then_the_full_allowance():
    points = walk(_base(1000, {2: -300}), TODAY, allowance=50, spent_today=20)

    assert [(p.date.day, p.balance, p.allowance) for p in points] == [
        (10, 970.0, 30.0),
        (11, 920.0, 50.0),
        (12, 570.0, 50.0),
        (13, 520.0, 50.0),
        (14, 470.0, 50.0),
    ]


def test_walk_overspent_today_takes_nothing_more():
    points = walk(_base(1000, {}), TODAY, allowance=50, spent_today=80)

    assert points[0].allowance == 0.0
    assert points[0].balance == 1000.0
    assert points[1].balance == 950.0


def test_walk_starting_after_today_spends_the_gap_days():
    later = TODAY + timedelta(days=3)

    points = walk(_base(1000, {}, start=later, days=1), TODAY, allowance=10, spent_today=4)

    # Today's remaining 6 plus two full days (11th and 12th) before the 13th,
    # then the 13th itself.
    assert points[0].balance == 1000 - 6 - 20 - 10


def test_walk_leaves_past_days_untouched():
    earlier = TODAY - timedelta(days=2)

    points = walk(_base(500, {}, start=earlier, days=3), TODAY, allowance=10)

    assert [p.balance for p in points] == [500.0, 500.0, 490.0]


def test_safe_daily_allowance_is_limited_by_the_tightest_day():
    # 1000 now, a 600 bill on day 2. Day 2 has three allowance days
    # (10th, 11th, 12th): (1000 - 600 - 100) / 3 = 100. The last day (14th)
    # allows (1000 - 600 - 100) / 5 = 60, which is tighter.
    base = _base(1000, {2: -600})

    assert safe_daily_allowance(base, TODAY, floor=100) == 60.0
    points = walk(base, TODAY, 60.0)
    assert min(p.balance for p in points) == 100.0


def test_safe_daily_allowance_is_zero_when_bills_alone_break_the_floor():
    assert safe_daily_allowance(_base(100, {1: -200}), TODAY, floor=0) == 0.0


def test_covered_until_is_the_last_day_before_the_dip():
    points = walk(_base(1000, {3: -1000}), TODAY, allowance=10)

    assert covered_until(points, TODAY, floor=0) == TODAY + timedelta(days=2)


def test_covered_until_runs_through_the_horizon_when_nothing_dips():
    points = walk(_base(1000, {}), TODAY, allowance=10)

    assert covered_until(points, TODAY, floor=0) == TODAY + timedelta(days=4)


def test_covered_until_is_none_when_today_is_already_below_the_floor():
    points = walk(_base(50, {}), TODAY, allowance=0)

    assert covered_until(points, TODAY, floor=100) is None


async def _checking(session: AsyncSession, user_id, workspace_id, name="Checking", type_="checking"):
    account = Account(
        id=uuid.uuid4(),
        user_id=user_id,
        workspace_id=workspace_id,
        name=name,
        type=type_,
        balance=Decimal("0"),
        currency="BRL",
    )
    session.add(account)
    await session.flush()
    return account


def _tx(user_id, workspace_id, account_id, amount, type_, day, **extra):
    return Transaction(
        id=uuid.uuid4(),
        user_id=user_id,
        workspace_id=workspace_id,
        account_id=account_id,
        description=extra.pop("description", "Row"),
        amount=Decimal(str(amount)),
        currency="BRL",
        date=day,
        type=type_,
        source=extra.pop("source", "manual"),
        **extra,
    )


@pytest.mark.asyncio
async def test_timeline_counts_bills_and_only_variable_spending_today(
    session: AsyncSession, test_user, test_workspace
):
    today = app_today()
    account = await _checking(session, test_user.id, test_workspace.id)
    loan = await _checking(session, test_user.id, test_workspace.id, "Car loan", "loan")
    rent = RecurringTransaction(
        id=uuid.uuid4(),
        user_id=test_user.id,
        workspace_id=test_workspace.id,
        account_id=account.id,
        description="Rent",
        amount=Decimal("700"),
        currency="BRL",
        type="debit",
        frequency="monthly",
        start_date=today + timedelta(days=5),
        next_occurrence=today + timedelta(days=5),
    )
    transfers = Category(
        id=uuid.uuid4(),
        user_id=test_user.id,
        workspace_id=test_workspace.id,
        name="Savings",
        treat_as_transfer=True,
    )
    session.add_all([rent, transfers])
    await session.flush()
    session.add_all([
        _tx(test_user.id, test_workspace.id, account.id, 2000, "credit", today - timedelta(days=1),
            source="opening_balance"),
        _tx(test_user.id, test_workspace.id, loan.id, 9000, "debit", today - timedelta(days=1),
            source="opening_balance"),
        # Variable spending today: counts.
        _tx(test_user.id, test_workspace.id, account.id, 30, "debit", today, description="iFood"),
        # A bill payment linked to its recurring is a fixed cost: does not count.
        _tx(test_user.id, test_workspace.id, account.id, 100, "debit", today,
            description="Internet", recurring_transaction_id=rent.id),
        # Moving money to savings is not spending.
        _tx(test_user.id, test_workspace.id, account.id, 200, "debit", today,
            description="To savings", category_id=transfers.id),
    ])
    await session.commit()
    await save_plan(session, test_workspace.id, SpendingPlanWrite(daily_allowance=Decimal("50")))

    timeline = await get_timeline(session, test_workspace.id, test_user.id)

    assert timeline.today.spent == 30.0
    assert timeline.today.remaining == 20.0
    # The loan stays out of the plan: 2000 - 330 spent today - 20 left today.
    assert timeline.points[0].date == today
    assert timeline.points[0].balance == 1650.0
    rent_day = next(p for p in timeline.points if p.date == today + timedelta(days=5))
    assert rent_day.balance == 1650.0 - 50 * 5 - 700
    assert timeline.covered_until is not None
    assert timeline.covered_until < timeline.horizon_end
    assert timeline.covered_through_horizon is False


@pytest.mark.asyncio
async def test_timeline_previews_an_allowance_without_a_saved_plan(
    session: AsyncSession, test_user, test_workspace
):
    today = app_today()
    account = await _checking(session, test_user.id, test_workspace.id)
    session.add(
        _tx(test_user.id, test_workspace.id, account.id, 1000, "credit", today - timedelta(days=1),
            source="opening_balance")
    )
    await session.commit()

    timeline = await get_timeline(session, test_workspace.id, test_user.id, Decimal("1"))

    assert timeline.daily_allowance == 1.0
    assert timeline.points[-1].date == timeline.horizon_end
    days = len(timeline.points)
    assert timeline.points[-1].balance == 1000.0 - days
    assert timeline.safe_daily_allowance == round(int(1000 / days * 100) / 100, 2)
    assert timeline.covered_through_horizon is True


@pytest.mark.asyncio
async def test_calendar_spends_the_allowance_only_for_the_plan_accounts(
    session: AsyncSession, test_user, test_workspace
):
    today = app_today()
    account = await _checking(session, test_user.id, test_workspace.id)
    savings = await _checking(session, test_user.id, test_workspace.id, "Savings", "savings")
    session.add_all([
        _tx(test_user.id, test_workspace.id, account.id, 1000, "credit", today - timedelta(days=40),
            source="opening_balance"),
        _tx(test_user.id, test_workspace.id, savings.id, 500, "credit", today - timedelta(days=40),
            source="opening_balance"),
    ])
    await session.commit()
    await save_plan(
        session,
        test_workspace.id,
        SpendingPlanWrite(daily_allowance=Decimal("10"), account_ids=[account.id]),
    )

    planned = await get_transaction_calendar(
        session, test_workspace.id, test_user.id, month=today, account_ids=[account.id]
    )
    savings_only = await get_transaction_calendar(
        session, test_workspace.id, test_user.id, month=today, account_ids=[savings.id]
    )

    planned_today = next(d for d in planned.days if d.date == today)
    assert planned_today.projected_allowance == 10.0
    assert planned_today.ending_balance == 990.0
    planned_yesterday = next(d for d in planned.days if d.date == today - timedelta(days=1))
    assert planned_yesterday.projected_allowance == 0.0
    assert planned_yesterday.ending_balance == 1000.0
    assert planned.spending_plan_applied is True
    assert savings_only.spending_plan_applied is False
    assert all(d.projected_allowance == 0.0 for d in savings_only.days)


@pytest.mark.asyncio
async def test_spending_plan_api_round_trip(client: AsyncClient, auth_headers: dict):
    empty = await client.get("/api/spending-plan", headers=auth_headers)
    assert empty.status_code == 200
    assert empty.json() is None

    saved = await client.put(
        "/api/spending-plan",
        headers=auth_headers,
        json={"daily_allowance": "45.50", "balance_floor": "200", "horizon_months": 18},
    )
    assert saved.status_code == 200
    assert saved.json() == {
        "daily_allowance": "45.50",
        "balance_floor": "200.00",
        "account_ids": None,
        "horizon_months": 18,
    }

    timeline = await client.get("/api/spending-plan/timeline", headers=auth_headers)
    assert timeline.status_code == 200
    body = timeline.json()
    assert body["daily_allowance"] == 45.5
    assert body["balance_floor"] == 200.0

    deleted = await client.delete("/api/spending-plan", headers=auth_headers)
    assert deleted.status_code == 204
    assert (await client.get("/api/spending-plan", headers=auth_headers)).json() is None
