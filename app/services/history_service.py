from sqlalchemy import desc, func, select

from app.database.db import SessionLocal
from app.database.models import Transaction, User


def _family_scope(family_id: int):
    return Transaction.user.has(User.family_id == family_id)


async def get_transactions_count(family_id: int):

    async with SessionLocal() as session:

        result = await session.execute(
            select(func.count(Transaction.id)).where(_family_scope(family_id))
        )

        return result.scalar() or 0


async def get_last_transactions(
    family_id: int,
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
            .where(User.family_id == family_id)
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
    family_id: int,
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
                User.family_id == family_id,
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
    family_id: int,
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
                User.family_id == family_id,
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
