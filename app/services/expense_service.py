from sqlalchemy import select

from app.database.db import SessionLocal
from app.database.models import Transaction
from app.services.parser import parse_message


async def save_transaction(text: str):

    parsed = parse_message(text)

    if parsed is None:
        return None

    async with SessionLocal() as session:

        transaction = Transaction(
            title=parsed["title"],
            amount=parsed["amount"],
            type=parsed["type"],
            category=parsed["category"],
        )

        session.add(transaction)

        await session.commit()

        await session.refresh(transaction)

        return transaction


async def get_transaction(transaction_id: int):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction).where(
                Transaction.id == transaction_id
            )
        )

        return result.scalar_one_or_none()