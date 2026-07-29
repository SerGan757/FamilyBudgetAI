from datetime import date

from app.services.parser import parse_message
from app.services.recurring_service import (
    add_payment,
    get_payments,
    delete_payment,
    get_generated_payment_ids,
    update_payment as update_payment_in_db,
)
from app.services.expense_service import create_transaction
from app.services.user_service import get_user_by_telegram_id
from app.database.models import Transaction


async def create_payment(text: str, telegram_id: int):

    parsed = parse_message(text)

    if parsed is None:
        return None

    user = await get_user_by_telegram_id(telegram_id)

    if user is None:
        return None

    return await add_payment(
        family_id=user.family_id,
        title=parsed["title"],
        amount=parsed["amount"],
        transaction_type=parsed["type"],
        category=parsed["category"],
    )


async def list_payments(telegram_id: int):
    user = await get_user_by_telegram_id(telegram_id)

    if user is None:
        return []

    return await get_payments(user.family_id)


async def remove_payment(payment_id: int, telegram_id: int):
    user = await get_user_by_telegram_id(telegram_id)

    if user is None:
        return False

    return await delete_payment(payment_id, user.family_id)


async def update_payment(
    payment_id: int,
    text: str,
    telegram_id: int,
):
    parsed = parse_message(text)

    if parsed is None:
        return None

    user = await get_user_by_telegram_id(telegram_id)

    if user is None:
        return None

    return await update_payment_in_db(
        payment_id=payment_id,
        family_id=user.family_id,
        title=parsed["title"],
        amount=parsed["amount"],
        transaction_type=parsed["type"],
        category=parsed["category"],
    )


async def create_month_transactions(telegram_id: int):
    from sqlalchemy import select, extract

    from app.database.db import SessionLocal
    from app.database.models import Transaction
    from app.services.expense_service import (
        create_transaction,
        update_recurring_transaction,
    )

    user = await get_user_by_telegram_id(telegram_id)

    if user is None:
        return {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "details": [],
        }

    period = date.today().replace(day=1)

    payments = await get_payments(
        user.family_id,
        active_only=True,
    )

    created = 0
    updated = 0
    unchanged = 0
    details = []

    async with SessionLocal() as session:

        for payment in payments:

            result = await session.execute(
                select(Transaction).where(
                    Transaction.recurring_payment_id == payment.id,
                    Transaction.recurring_period == period,
                )
            )

            transaction = result.scalar_one_or_none()

            if transaction is None:

                await create_transaction(
                    user_id=user.id,
                    title=payment.title,
                    amount=payment.amount,
                    transaction_type=payment.type,
                    category=payment.category,
                    is_recurring=True,
                    recurring_payment_id=payment.id,
                    recurring_period=period,
                )

                created += 1

                ddetails.append(
                    {
                        "title": payment.title,
                        "amount": payment.amount,
                        "type": payment.type,
                        "status": "created",
                    }
                )


                continue

            if (
                transaction.title != payment.title
                or transaction.amount != payment.amount
                or transaction.category != payment.category
            ):

                await update_recurring_transaction(
                    transaction=transaction,
                    title=payment.title,
                    amount=payment.amount,
                    category=payment.category,
                )

                updated += 1

                details.append(
                    {
                        "title": payment.title,
                        "amount": payment.amount,
                        "type": payment.type,
                        "status": "updated",
                    }
                )

            else:

                unchanged += 1

                details.append(
                    {
                        "title": payment.title,
                        "amount": payment.amount,
                        "type": payment.type,
                        "status": "unchanged",
                    }
                )

    return {
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "details": details,
    }

from datetime import date

from sqlalchemy import extract, select
from sqlalchemy.orm import selectinload

from app.database.db import SessionLocal
from app.database.models import Transaction


async def get_month_recurring_transactions(telegram_id: int):

    from datetime import date

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    user = await get_user_by_telegram_id(telegram_id)

    if user is None:
        return []

    period = date.today().replace(day=1)

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction)
            .options(
                selectinload(Transaction.user)
            )
            .where(
                Transaction.is_recurring.is_(True),
                Transaction.recurring_period == period,
                Transaction.recurring_payment_id.is_not(None),
                Transaction.user.has(
                    family_id=user.family_id
                ),
            )
            .order_by(
                Transaction.title
            )
        )

        transactions = result.scalars().all()

        unique = {}

        for transaction in transactions:
            unique[transaction.recurring_payment_id] = transaction

        return list(unique.values())