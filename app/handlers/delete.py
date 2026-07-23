from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.keyboards.main_menu import main_menu
from app.services.delete_service import (
    delete_last_transaction,
    delete_transaction_by_id,
    delete_transactions_by_ids,
)
from app.services.history_service import get_last_transactions

router = Router()

# -------------------------------------------------------------------
# Старый режим удаления по ID (временно оставляем)
# -------------------------------------------------------------------

waiting_for_delete_id = set()
waiting_for_multiple_delete = set()


def operation_card(transaction) -> str:

    sign = "+" if transaction.type == "income" else "-"

    if transaction.type == "income":
        icon = "💰"
    else:
        icon = transaction.category.split()[0]

    return (
        "<pre>"
        "🗑️ Операция удалена\n"
        "────────────────────────────\n\n"
        f"{icon} {transaction.title}\n"
        f"{sign}{transaction.amount:.2f} €"
        "</pre>"
    )

def format_history_line(transaction) -> str:

    sign = "+" if transaction.type == "income" else "-"

    amount = (
        f"{sign}{transaction.amount:.2f}€/м"
        if transaction.is_recurring
        else f"{sign}{transaction.amount:.2f}€"
    )

    icon = (
        "💰"
        if transaction.type == "income"
        else transaction.category.split()[0]
    )

    return (
        f"<code>{transaction.id:>4}</code> │ "
        f"{icon} {transaction.title[:18]:<18} │ "
        f"{amount:<10} │ "
        f"{transaction.user_name}"
    )

# -------------------------------------------------------------------
# Удалить последнюю операцию
# -------------------------------------------------------------------

@router.message(F.text == "🗑️ Удалить")
async def delete(message: Message):

    waiting_for_multiple_delete.add(
        message.from_user.id
    )

    await message.answer(
        "<b>🗑 Удаление операций</b>\n\n"
        "Введите ID операции.\n\n"
        "Можно указать несколько ID через пробел.\n\n"
        "<pre>"
        "125\n"
        "125 126 130"
        "</pre>",
        reply_markup=main_menu,
    )


# -------------------------------------------------------------------
# Старое удаление через меню
# -------------------------------------------------------------------

@router.message(F.text.regexp(r"^[\d,\s]+$"))
async def delete_multiple(message: Message):

    if message.from_user.id not in waiting_for_multiple_delete:
        return

    waiting_for_multiple_delete.remove(
        message.from_user.id
    )

    text = (
        message.text
        .replace(",", " ")
        .split()
    )

    ids = []

    for value in text:
        try:
            ids.append(int(value))
        except ValueError:
            pass

    if not ids:
        return

    deleted = await delete_transactions_by_ids(ids)

    if not deleted:
        await message.answer(
            "Ни одной операции не найдено.",
            reply_markup=main_menu,
        )
        return

    result = f"🗑 Удалено операций: {len(deleted)}\n\n"

    for transaction in deleted:
        sign = "+" if transaction.type == "income" else "-"

        result += (
            f"✅ ID {transaction.id} "
            f"{transaction.title} "
            f"{sign}{transaction.amount:.2f} €\n"
        )

    await message.answer(
        result,
        reply_markup=main_menu,
    )

    transactions = await get_last_transactions()

    if transactions:

        history_text = "<b>📋 Последние операции</b>\n\n"

        for transaction in transactions:
            history_text += (
                format_history_line(transaction)
                + "\n"
            )

        await message.answer(
            history_text,
            reply_markup=main_menu,
        )
# -------------------------------------------------------------------
# Новое удаление из истории
# -------------------------------------------------------------------

@router.callback_query(
    F.data.startswith("hist_delete:")
)
async def history_delete_callback(
    callback: CallbackQuery,
):

    transaction_id = int(
        callback.data.split(":")[1]
    )

    transaction = await delete_transaction_by_id(
        transaction_id
    )

    if transaction is None:

        await callback.answer(
            "Операция уже удалена.",
            show_alert=True,
        )

        return

    await callback.message.edit_text(
        operation_card(transaction)
    )

    await callback.answer(
        "Удалено"
    )