from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.keyboards.pagination_keyboard import pagination_keyboard
from app.services.history_service import (
    get_last_transactions,
    get_transactions_count,
)
from app.services.family_context_service import require_family_for_chat
from app.utils.navigation import show_back_keyboard

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

    base_icon = (
        "💰"
        if transaction.type == "income"
        else escape(transaction.category.split()[0])
    )

    icon = (
        f"🔁 {base_icon}"
        if transaction.is_recurring
        else base_icon
    )

    title = escape(transaction.title)

    if len(title) > 18:
        title = title[:17] + "…"

    user = (
        escape(transaction.user_name[:3])
        if transaction.user_name
        else ""
    )

    return (
        f"{transaction.id} {icon} {title} {amount_text} {user}"
    )


async def build_history_text(family_id: int, offset: int = 0):

    total = await get_transactions_count(family_id)

    transactions = await get_last_transactions(
        family_id=family_id,
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
    family = await require_family_for_chat(message.chat.id)
    total = await get_transactions_count(family.id)

    await message.answer(
        await build_history_text(family.id, 0),
        reply_markup=pagination_keyboard(
            prefix="history",
            offset=0,
            total=total,
            limit=LIMIT,
        ),
    )
    await show_back_keyboard(message)


@router.callback_query(
    F.data.startswith("history:")
)
async def history_page(
    callback: CallbackQuery,
):

    offset = int(
        callback.data.split(":")[1]
    )

    family = await require_family_for_chat(callback.message.chat.id)
    total = await get_transactions_count(family.id)

    await callback.message.edit_text(
        await build_history_text(family.id, offset),
        reply_markup=pagination_keyboard(
            prefix="history",
            offset=offset,
            total=total,
            limit=LIMIT,
        ),
    )

    await callback.answer()
