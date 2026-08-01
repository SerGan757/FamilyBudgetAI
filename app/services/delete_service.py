from sqlalchemy import delete, desc, select

from app.database.db import SessionLocal
from app.database.models import Transaction, User


async def delete_transactions_by_ids(ids: list[int], family_id: int):

    deleted = []

    for transaction_id in ids:

        transaction = await delete_transaction_by_id(
            transaction_id, family_id
        )

        if transaction:
            deleted.append(transaction)

    return deleted

async def delete_last_transaction(family_id: int):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction).where(Transaction.family_id == family_id)
            .order_by(desc(Transaction.id))
            .limit(1)
        )

        transaction = result.scalar_one_or_none()

        if transaction is None:
            return None

        await session.delete(transaction)
        await session.commit()

        return transaction


async def delete_transaction_by_id(transaction_id: int, family_id: int):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction).where(
                Transaction.id == transaction_id,
                Transaction.family_id == family_id,
            )
        )

        transaction = result.scalar_one_or_none()

        if transaction is None:
            return None

        await session.delete(transaction)
        await session.commit()

        return transaction
