from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.services.history_service import get_last_transactions

router = Router()


def format_transaction(transaction) -> str:

    sign = "+" if transaction.type == "income" else "-"

    amount = (
        f"{sign}{transaction.amount:.2f}€/м"
        if transaction.is_recurring
        else f"{sign}{transaction.amount:.2f}€"
    )

    if transaction.type == "income":
        icon = "💰"
    else:
        icon = transaction.category.split()[0]

    title = transaction.title[:18]
    user = transaction.user_name[:10]

    return (
        "<code>"
        f"{transaction.id:>4} │ "
        f"{icon} {title:<18} │ "
        f"{amount:>13} │ "
        f"{user:<10}"
        "</code>"
    )


@router.message(Command("history"))
async def history(message: Message):

    transactions = await get_last_transactions()

    if not transactions:
        await message.answer("📋 История пуста.")
        return

    text = (
    "<b>📋 Последние 20 операций</b>\n\n"
    )

    text += (
        "<code>"
        " ID │ Операция            │        Сумма │ Пользователь\n"
        "────┼─────────────────────┼──────────────┼────────────"
        "</code>\n"
   )

    for transaction in transactions:
        text += (
    format_transaction(transaction)
    + "\n"
    )

    text += (
        "\n"
        "<b>Введите ID операции для удаления.</b>\n\n"
        "Можно указать несколько ID.\n\n"
        "<pre>"
        "154\n"
        "154 152\n"
        "154,152,150"
        "</pre>"
    )

    await message.answer(
        text
    )