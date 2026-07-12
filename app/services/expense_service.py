from app.database.db import SessionLocal
from app.database.models import Transaction


async def save_transaction(data: dict):

    async with SessionLocal() as session:

        transaction = Transaction(
            type=data["type"],
            title=data["title"],
            category=data["category"],
            amount=data["amount"],
        )

        session.add(transaction)
        await session.commit()

        return transaction