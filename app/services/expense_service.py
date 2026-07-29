from datetime import date

from sqlalchemy import select

from app.database.db import SessionLocal
from app.database.models import Transaction
from app.services.parser import parse_message
from app.services.user_service import get_user_by_telegram_id


async def save_transaction(
    text: str,
    telegram_id: int,
):

    parsed = parse_message(text)

    if parsed is None:
        return "PARSE_ERROR"

    user = await get_user_by_telegram_id(telegram_id)

    if user is None:
        return "USER_NOT_FOUND"

    transaction = await create_transaction(
        user_id=user.id,
        title=parsed["title"],
        amount=parsed["amount"],
        transaction_type=parsed["type"],
        category=parsed["category"],
    )

    return transaction


async def create_transaction(
    user_id: int,
    title: str,
    amount: float,
    transaction_type: str = "expense",
    category: str = "📦 Прочее",
    is_recurring: bool = False,
    recurring_payment_id: int | None = None,
    recurring_period: date | None = None,
):

    async with SessionLocal() as session:

        transaction = Transaction(
            user_id=user_id,
            title=title,
            amount=amount,
            type=transaction_type,
            category=category,
            is_recurring=is_recurring,
            recurring_payment_id=recurring_payment_id,
            recurring_period=recurring_period,
        )

        session.add(transaction)

        await session.commit()

        await session.refresh(transaction)

        return transaction


async def update_recurring_transaction(
    transaction: Transaction,
    title: str,
    amount: float,
    transaction_type: str,
    category: str,
):

    async with SessionLocal() as session:

        db_transaction = await session.get(
            Transaction,
            transaction.id,
        )

        if db_transaction is None:
            return None

        db_transaction.title = title
        db_transaction.amount = amount
        db_transaction.type = transaction_type
        db_transaction.category = category

        await session.commit()
        await session.refresh(db_transaction)

        return db_transaction        


async def get_transaction(transaction_id: int):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction).where(
                Transaction.id == transaction_id
            )
        )

        return result.scalar_one_or_none()
