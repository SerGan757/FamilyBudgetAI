from sqlalchemy import select

from app.database.db import SessionLocal
from app.database.models import Transaction, User


async def get_balance(family_id: int):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction).where(Transaction.family_id == family_id)
        )

        transactions = result.scalars().all()

        income = 0
        expense = 0

        for t in transactions:

            if t.type == "income":
                income += t.amount
            else:
                expense += t.amount

        return income, expense, income - expense
