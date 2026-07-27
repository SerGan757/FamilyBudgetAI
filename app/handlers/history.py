from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.keyboards.pagination_keyboard import pagination_keyboard
from app.services.history_service import (
    get_last_transactions,
    get_transactions_count,
)

router = Router()

LIMIT = 20


def format_transaction(transaction) -> str:

    sign = "+" if transaction.type == "income" else "-"

    amount = abs(transaction.amount)

    if amount.is_integer():
        amount_text = f"{sign}{int(amount)} €"
    else:
        amount_text = f"{sign}{amount:.2f} €"

    if transaction.is_recurring:
        amount_text += "/мес"

    icon = (
        "💰"
        if transaction.type == "income"
        else transaction.category.split()[0]
    )

    title = transaction.title

    if len(title) > 18:
        title = title[:17] + "…"

    user = transaction.user_name[:3]

    return (
        f"{transaction.id} {icon} {title} {amount_text} {user}"
    )


async def build_history_text(offset: int = 0):

    total = await get_transactions_count()

    transactions = await get_last_transactions(
        limit=LIMIT,
        offset=offset,
    )

    if not transactions:
        return "📋 История пуста."

    text = (
        "<b>📋 История операций</b>\n\n"
    )

    for transaction in transactions:
        text += (
            format_transaction(transaction)
            + "\n"
        )

    shown = min(
        offset + LIMIT,
        total,
    )

    text += (
        f"\n<b>Показано: {shown} из {total}</b>"
    )

    return text

@router.message(Command("history"))
async def history(message: Message):

    total = await get_transactions_count()

    await message.answer(
        await build_history_text(0),
        reply_markup=pagination_keyboard(
            prefix="history",
            offset=0,
            total=total,
            limit=LIMIT,
        ),
    )


@router.callback_query(
    F.data.startswith("history:")
)
async def history_page(
    callback: CallbackQuery,
):

    offset = int(
        callback.data.split(":")[1]
    )

    total = await get_transactions_count()

    await callback.message.edit_text(
        await build_history_text(offset),
        reply_markup=pagination_keyboard(
            prefix="history",
            offset=offset,
            total=total,
            limit=LIMIT,
        ),
    )

    await callback.answer()