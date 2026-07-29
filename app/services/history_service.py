from sqlalchemy import desc, func, select

from app.database.db import SessionLocal
from app.database.models import Transaction, User


async def get_transactions_count():

    async with SessionLocal() as session:

        result = await session.execute(
            select(func.count(Transaction.id))
        )

        return result.scalar() or 0


async def get_last_transactions(
    limit: int = 20,
    offset: int = 0,
):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction, User)
            .join(
                User,
                Transaction.user_id == User.id,
            )
            .order_by(
                desc(Transaction.id)
            )
            .offset(offset)
            .limit(limit)
        )

        rows = result.all()

        transactions = []

        for transaction, user in rows:

            transaction.user_name = user.name

            transactions.append(transaction)

        return transactions


async def get_transactions_by_category(
    category: str,
    limit: int = 20,
    offset: int = 0,
):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction, User)
            .join(
                User,
                Transaction.user_id == User.id,
            )
            .where(
                Transaction.category == category
            )
            .order_by(
                desc(Transaction.id)
            )
            .offset(offset)
            .limit(limit)
        )

        rows = result.all()

        transactions = []

        for transaction, user in rows:

            transaction.user_name = user.name

            transactions.append(transaction)

        return transactions


async def get_transactions_by_type(
    transaction_type: str,
    limit: int = 20,
    offset: int = 0,
):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction, User)
            .join(
                User,
                Transaction.user_id == User.id,
            )
            .where(
                Transaction.type == transaction_type
            )
            .order_by(
                desc(Transaction.id)
            )
            .offset(offset)
            .limit(limit)
        )

        rows = result.all()

        transactions = []

        for transaction, user in rows:

            transaction.user_name = user.name

            transactions.append(transaction)

        return transactions