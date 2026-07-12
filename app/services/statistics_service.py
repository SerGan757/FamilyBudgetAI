from datetime import datetime, time

from sqlalchemy import select

from app.database.db import SessionLocal
from app.database.models import Transaction


async def get_today_transactions():

    start = datetime.combine(datetime.today(), time.min)

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction)
            .where(Transaction.created_at >= start)
            .order_by(Transaction.created_at)
        )

        return result.scalars().all()


async def get_month_transactions():

    start = datetime.today().replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction)
            .where(Transaction.created_at >= start)
            .order_by(Transaction.created_at)
        )

        return result.scalars().all()


async def get_month_summary():

    transactions = await get_month_transactions()

    income = 0
    expense = 0

    for t in transactions:
        if t.type == "income":
            income += t.amount
        else:
            expense += t.amount

    return transactions, income, expense