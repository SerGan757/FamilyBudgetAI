from aiogram import F, Router
from html import escape
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.services.delete_service import (
    delete_last_transaction,
    delete_transaction_by_id,
    delete_transactions_by_ids,
)
from app.services.history_service import get_last_transactions
from app.handlers.user_states import DeleteState
from app.keyboards.main_menu import back_to_main_menu_keyboard
from app.services.user_service import get_user_by_telegram_id

router = Router()

# -------------------------------------------------------------------
# Старый режим удаления по ID (временно оставляем)
# -------------------------------------------------------------------


def operation_card(transaction) -> str:

    sign = "+" if transaction.type == "income" else "-"

    if transaction.type == "income":
        icon = "💰"
    else:
        icon = escape(transaction.category.split()[0])

    return (
        "<pre>"
        "🗑️ Операция удалена\n"
        "────────────────────────────\n\n"
        f"{icon} {escape(transaction.title)}\n"
        f"{sign}{transaction.amount:.2f} €"
        "</pre>"
    )

def format_history_line(transaction) -> str:
    sign = "+" if transaction.type == "income" else "-"
    amount = (
        f"{sign}{transaction.amount:.2f} €/мес"
        if transaction.is_recurring
        else f"{sign}{transaction.amount:.2f} €"
    )

    base_icon = (
        "💰"
        if transaction.type == "income"
        else escape(transaction.category.split()[0])
    )
    icon = f"🔄{base_icon}" if transaction.is_recurring else base_icon
    title = escape(transaction.title)
    if len(title) > 24:
        title = title[:23] + "…"
    return f"{transaction.id}. {icon} {title} {amount} {escape(transaction.user_name)}"

# -------------------------------------------------------------------
# Удалить последнюю операцию
# -------------------------------------------------------------------

@router.message(F.text == "🗑️ Удалить")
async def delete(message: Message, state: FSMContext):

    await state.set_state(DeleteState.waiting_for_ids)

    await message.answer(
        "<b>🗑 Удаление операций</b>\n\n"
        "Введите ID операции.\n\n"
        "Можно указать несколько ID через пробел.\n\n"
        "<pre>"
        "125\n"
        "125 126 130"
        "</pre>",
        reply_markup=back_to_main_menu_keyboard,
    )


# -------------------------------------------------------------------
# Старое удаление через меню
# -------------------------------------------------------------------

@router.message(DeleteState.waiting_for_ids, F.text.regexp(r"^[\d,\s]+$"))
async def delete_multiple(message: Message, state: FSMContext):

    user = await get_user_by_telegram_id(message.from_user.id)
    if user is None:
        await state.clear()
        return

    await state.clear()

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

    deleted = await delete_transactions_by_ids(ids, user.family_id)

    if not deleted:
        await message.answer(
            "Ни одной операции не найдено.",
            reply_markup=back_to_main_menu_keyboard,
        )
        return

    result = f"🗑 Удалено операций: {len(deleted)}\n\n"

    for transaction in deleted:
        sign = "+" if transaction.type == "income" else "-"

        result += (
            f"✅ ID {transaction.id} "
            f"{escape(transaction.title)} "
            f"{sign}{transaction.amount:.2f} €\n"
        )

    await message.answer(
        result,
        reply_markup=back_to_main_menu_keyboard,
    )

    transactions = await get_last_transactions(user.family_id)

    if transactions:

        history_text = "<b>📋 Последние операции</b>\n\n"

        for transaction in transactions:
            history_text += (
                format_history_line(transaction)
                + "\n"
            )

        await message.answer(
            history_text,
            reply_markup=back_to_main_menu_keyboard,
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

    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    transaction = await delete_transaction_by_id(transaction_id, user.family_id)

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
