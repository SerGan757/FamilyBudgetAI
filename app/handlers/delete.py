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
from app.keyboards.main_menu import back_to_main_menu
from app.services.family_context_service import require_family_for_chat
from app.utils.transaction_format import project_suffix
from app.utils.currency import family_currency, format_money
from app.i18n import all_texts, family_language, t

router = Router()

# -------------------------------------------------------------------
# Старый режим удаления по ID (временно оставляем)
# -------------------------------------------------------------------


def operation_card(transaction, currency_code: str = "EUR", language: str = "ru") -> str:

    sign = "+" if transaction.type == "income" else "-"

    if transaction.type == "income":
        icon = "💰"
    else:
        icon = escape(transaction.category.split()[0])

    return (
        "<pre>"
        f"{t(language, 'delete.operation_deleted')}\n"
        "────────────────────────────\n\n"
        f"{icon} {escape(transaction.title)}\n"
        f"{sign}{format_money(transaction.amount, currency_code)}"
        "</pre>"
    )

def format_history_line(transaction, currency_code: str = "EUR", language: str = "ru") -> str:
    sign = "+" if transaction.type == "income" else "-"
    amount = (
        f"{sign}{format_money(transaction.amount, currency_code)}/{t(language, 'common.monthly')}"
        if transaction.is_recurring
        else f"{sign}{format_money(transaction.amount, currency_code)}"
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
    return (
        f"{transaction.id}. {icon} {title} {amount} {escape(transaction.user_name)}"
        f"{project_suffix(transaction)}"
    )

# -------------------------------------------------------------------
# Удалить последнюю операцию
# -------------------------------------------------------------------

@router.message(F.text.in_(all_texts("menu.delete")))
async def delete(message: Message, state: FSMContext):

    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type, telegram_id=message.from_user.id,
    )
    language = family_language(family)

    await state.set_state(DeleteState.waiting_for_ids)

    await message.answer(
        f"<b>{t(language, 'delete.title')}</b>\n\n"
        f"{t(language, 'delete.instruction')}\n\n"
        f"{t(language, 'delete.multiple')}\n\n"
        "<pre>"
        "125\n"
        "125 126 130"
        "</pre>",
        reply_markup=back_to_main_menu(language),
    )


# -------------------------------------------------------------------
# Старое удаление через меню
# -------------------------------------------------------------------

@router.message(DeleteState.waiting_for_ids, F.text.regexp(r"^[\d,\s]+$"))
async def delete_multiple(message: Message, state: FSMContext):

    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type,
        telegram_id=message.from_user.id,
    )
    language = family_language(family)

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

    deleted = await delete_transactions_by_ids(ids, family.id)

    if not deleted:
        await message.answer(
            t(language, "delete.not_found"),
            reply_markup=back_to_main_menu(language),
        )
        return

    result = f"{t(language, 'delete.deleted_count', count=len(deleted))}\n\n"

    for transaction in deleted:
        sign = "+" if transaction.type in ("income", "goal_contribution") else "-"

        result += (
            f"✅ ID {transaction.id} "
            f"{escape(transaction.title)} "
            f"{sign}{format_money(transaction.amount, family_currency(family))}\n"
        )

    await message.answer(
        result,
        reply_markup=back_to_main_menu(language),
    )

    transactions = await get_last_transactions(family.id)

    if transactions:

        history_text = f"<b>{t(language, 'delete.recent')}</b>\n\n"

        for transaction in transactions:
            history_text += (
                format_history_line(transaction, family_currency(family), language)
                + "\n"
            )

        await message.answer(
            history_text,
            reply_markup=back_to_main_menu(language),
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

    family = await require_family_for_chat(
        callback.message.chat.id, chat_type=callback.message.chat.type,
        telegram_id=callback.from_user.id,
    )
    language = family_language(family)
    transaction = await delete_transaction_by_id(transaction_id, family.id)

    if transaction is None:

        await callback.answer(
            t(language, "delete.already_deleted"),
            show_alert=True,
        )

        return

    await callback.message.edit_text(
        operation_card(transaction, family_currency(family), language)
    )

    await callback.answer(
        t(language, "delete.deleted")
    )
