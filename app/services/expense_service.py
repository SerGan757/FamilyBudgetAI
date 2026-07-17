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
        return None

    user = await get_user_by_telegram_id(telegram_id)

    if user is None:
        return None

    return await create_transaction(
        user_id=user.id,
        title=parsed["title"],
        amount=parsed["amount"],
        transaction_type=parsed["type"],
        category=parsed["category"],
    )


async def create_transaction(
    user_id: int,
    title: str,
    amount: float,
    transaction_type: str = "expense",
    category: str = "📦 Прочее",
    is_recurring: bool = False,
    recurring_payment_id: int | None = None,
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