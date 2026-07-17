from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.services.history_service import get_last_transactions

router = Router()


def format_transaction(transaction):

    sign = "+" if transaction.type == "income" else "-"

    amount = (
        f"{sign}{transaction.amount:.2f} €/мес"
        if transaction.is_recurring
        else f"{sign}{transaction.amount:.2f} €"
    )

    icon = transaction.category.split()[0]

    title = transaction.title[:20]
    user = transaction.user_name[:10]

    return (
        f"{icon} "
        f"{title:<20}"
        f"{amount:>12}"
        f"  {user}"
    )


@router.message(Command("history"))
async def history(message: Message):

    transactions = await get_last_transactions()

    if not transactions:
        await message.answer("📋 История пуста.")
        return

    text = "<pre>📋 ИСТОРИЯ\n\n"

    for transaction in transactions:
        text += format_transaction(transaction) + "\n"

    text += "</pre>"

    await message.answer(text)