from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.services.history_service import get_last_transactions

router = Router()


def format_transaction(transaction):

    if transaction.type == "income":
        sign = "+"
    else:
        sign = "-"

    return (
        f"{transaction.id:<4}"
        f"{transaction.category:<18}"
        f"{transaction.title[:22]:<22}"
        f"{sign}{transaction.amount:>8.2f} €"
    )


@router.message(Command("history"))
async def history(message: Message):

    transactions = await get_last_transactions()

    if not transactions:
        await message.answer("📋 История пуста.")
        return

    text = (
        "<pre>"
        "📋 ИСТОРИЯ ОПЕРАЦИЙ\n"
        "══════════════════════════════════════════════\n"
    )

    for transaction in transactions:

        text += (
            format_transaction(transaction)
            + "\n"
        )

    text += (
        "══════════════════════════════════════════════\n"
        f"Всего показано: {len(transactions)}"
        "</pre>"
    )

    await message.answer(text)