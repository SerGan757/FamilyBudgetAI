from app.services.parser import parse_message
from app.services.recurring_service import (
    add_payment,
    get_payments,
    delete_payment,
)
from app.services.expense_service import create_transaction


async def create_payment(text: str):

    parsed = parse_message(text)

    if parsed is None:
        return None

    return await add_payment(
        title=parsed["title"],
        amount=parsed["amount"],
        category=parsed["category"],
    )


async def list_payments():

    return await get_payments()


async def remove_payment(payment_id: int):

    await delete_payment(payment_id)


async def create_month_transactions():

    payments = await get_payments()

    created = 0

    for payment in payments:

        await create_transaction(
            title=payment.title,
            amount=payment.amount,
            transaction_type="expense",
            category=payment.category,
            is_recurring=True,
            recurring_payment_id=payment.id,
        )

        created += 1

    return created