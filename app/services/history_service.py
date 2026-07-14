from sqlalchemy import desc, select

from app.database.db import SessionLocal
from app.database.models import Transaction


async def get_last_transactions(limit: int = 10):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction)
            .order_by(desc(Transaction.id))
            .limit(limit)
        )

        return result.scalars().all()


async def get_transactions_by_category(category: str):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction)
            .where(Transaction.category == category)
            .order_by(desc(Transaction.id))
        )

        return result.scalars().all()


async def get_transactions_by_type(transaction_type: str):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction)
            .where(Transaction.type == transaction_type)
            .order_by(desc(Transaction.id))
        )

        return result.scalars().all()