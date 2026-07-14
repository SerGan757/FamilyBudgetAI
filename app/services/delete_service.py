from sqlalchemy import delete, desc, select

from app.database.db import SessionLocal
from app.database.models import Transaction


async def delete_last_transaction():

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction)
            .order_by(desc(Transaction.id))
            .limit(1)
        )

        transaction = result.scalar_one_or_none()

        if transaction is None:
            return None

        await session.delete(transaction)
        await session.commit()

        return transaction


async def delete_transaction_by_id(transaction_id: int):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction).where(
                Transaction.id == transaction_id
            )
        )

        transaction = result.scalar_one_or_none()

        if transaction is None:
            return None

        await session.delete(transaction)
        await session.commit()

        return transaction