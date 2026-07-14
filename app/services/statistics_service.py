from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from app.database.db import SessionLocal
from app.database.models import Transaction


async def _sum(transaction_type: str, start=None, end=None):

    async with SessionLocal() as session:

        query = (
            select(func.coalesce(func.sum(Transaction.amount), 0.0))
            .where(Transaction.type == transaction_type)
        )

        # Если в модели есть created_at
        if hasattr(Transaction, "created_at"):

            if start is not None:
                query = query.where(Transaction.created_at >= start)

            if end is not None:
                query = query.where(Transaction.created_at < end)

        result = await session.execute(query)

        return float(result.scalar() or 0)


async def get_today_statistics():

    today = datetime.combine(date.today(), datetime.min.time())
    tomorrow = today + timedelta(days=1)

    income = await _sum(
        "income",
        today,
        tomorrow,
    )

    expense = await _sum(
        "expense",
        today,
        tomorrow,
    )

    return income, expense


async def get_month_statistics():

    today = date.today()

    month_start = datetime(
        today.year,
        today.month,
        1,
    )

    if today.month == 12:

        next_month = datetime(
            today.year + 1,
            1,
            1,
        )

    else:

        next_month = datetime(
            today.year,
            today.month + 1,
            1,
        )

    income = await _sum(
        "income",
        month_start,
        next_month,
    )

    expense = await _sum(
        "expense",
        month_start,
        next_month,
    )

    return income, expense


async def get_balance():

    income = await _sum("income")

    expense = await _sum("expense")

    return income, expense


async def get_category_statistics():

    async with SessionLocal() as session:

        result = await session.execute(
            select(
                Transaction.category,
                func.sum(Transaction.amount),
            )
            .where(Transaction.type == "expense")
            .group_by(Transaction.category)
            .order_by(func.sum(Transaction.amount).desc())
        )

        return result.all()