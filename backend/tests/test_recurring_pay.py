"""Paying a recurring bill before it is due."""
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.transaction import Transaction
from app.schemas.recurring_transaction import RecurringTransactionCreate
from app.schemas.transaction import TransactionCreate
from app.services.recurring_transaction_service import (
    create_recurring_transaction,
    generate_pending,
)
from app.services.transaction_service import create_transaction


@pytest_asyncio.fixture
async def account(session: AsyncSession, test_user, test_workspace) -> Account:
    acc = Account(
        id=uuid.uuid4(),
        user_id=test_user.id,
        workspace_id=test_workspace.id,
        name="Carteira",
        type="checking",
        balance=Decimal("10000"),
        currency="BRL",
    )
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    return acc


async def _make_bill(session, test_workspace, test_user, account, **overrides):
    data = RecurringTransactionCreate(
        description=overrides.pop("description", "Internet Fibra"),
        amount=overrides.pop("amount", Decimal("120.00")),
        currency="BRL",
        type="debit",
        frequency="monthly",
        start_date=overrides.pop("start_date", date(2025, 1, 10)),
        account_id=account.id,
        **overrides,
    )
    return await create_recurring_transaction(session, test_workspace.id, test_user.id, data)


async def _rows_for(session, bill_id):
    result = await session.execute(
        select(Transaction).where(Transaction.recurring_transaction_id == bill_id)
    )
    return list(result.scalars())


@pytest.mark.asyncio
async def test_manual_early_payment_settles_the_occurrence(
    session, test_user, test_workspace, account
):
    bill = await _make_bill(session, test_workspace, test_user, account)

    tx = await create_transaction(
        session,
        test_workspace.id,
        test_user.id,
        TransactionCreate(
            description="Internet Fibra",
            amount=Decimal("120.00"),
            date=date(2025, 1, 7),
            type="debit",
            account_id=account.id,
        ),
    )

    assert tx.recurring_transaction_id == bill.id
    await session.refresh(bill)
    assert bill.next_occurrence == date(2025, 2, 10)

    generated = await generate_pending(session, test_user.id, up_to=date(2025, 1, 10))
    assert generated == 0
    assert [row.id for row in await _rows_for(session, bill.id)] == [tx.id]


@pytest.mark.asyncio
async def test_manual_installment_is_never_linked_to_a_bill(
    session, test_user, test_workspace, account
):
    bill = await _make_bill(session, test_workspace, test_user, account)

    tx = await create_transaction(
        session,
        test_workspace.id,
        test_user.id,
        TransactionCreate(
            description="Internet Fibra",
            amount=Decimal("120.00"),
            date=date(2025, 1, 9),
            type="debit",
            account_id=account.id,
            installment_number=1,
            total_installments=3,
            installment_total_amount=Decimal("360.00"),
            installment_purchase_date=date(2025, 1, 9),
        ),
    )

    assert tx.recurring_transaction_id is None
    await session.refresh(bill)
    assert bill.next_occurrence == date(2025, 1, 10)
