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
        category=parsed["category"],
    )


async def create_month_transactions(telegram_id: int):
    user = await get_user_by_telegram_id(telegram_id)

    if user is None:
        return 0

    period = date.today().replace(day=1)

    payments = await get_payments(
        user.family_id,
        active_only=True,
    )

    generated_payment_ids = await get_generated_payment_ids(
        user.family_id,
        period,
    )

    created = 0

    for payment in payments:

        if payment.id in generated_payment_ids:
            continue

        await create_transaction(
            user_id=user.id,
            title=payment.title,
            amount=payment.amount,
            transaction_type="expense",
            category=payment.category,
            is_recurring=True,
            recurring_payment_id=payment.id,
            recurring_period=period,
        )

        created += 1

    return created
