from sqlalchemy import desc, select

from app.database.db import SessionLocal
from app.database.models import Transaction, User


async def get_last_transactions(limit: int = 10):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction, User)
            .join(User, Transaction.user_id == User.id)
            .order_by(desc(Transaction.id))
            .limit(limit)
        )

        rows = result.all()

        transactions = []

        for transaction, user in rows:

            if transaction.is_recurring:
                transaction.title = f"🔁 {transaction.title}"

            transaction.user_name = user.name

            transactions.append(transaction)

        return transactions


async def get_transactions_by_category(category: str):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction, User)
            .join(User, Transaction.user_id == User.id)
            .where(Transaction.category == category)
            .order_by(desc(Transaction.id))
        )

        rows = result.all()

        transactions = []

        for transaction, user in rows:

            if transaction.is_recurring:
                transaction.title = f"🔁 {transaction.title}"

            transaction.user_name = user.name

            transactions.append(transaction)

        return transactions


async def get_transactions_by_type(transaction_type: str):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction, User)
            .join(User, Transaction.user_id == User.id)
            .where(Transaction.type == transaction_type)
            .order_by(desc(Transaction.id))
        )

        rows = result.all()

        transactions = []

        for transaction, user in rows:

            if transaction.is_recurring:
                transaction.title = f"🔁 {transaction.title}"

            transaction.user_name = user.name

            transactions.append(transaction)

        return transactions