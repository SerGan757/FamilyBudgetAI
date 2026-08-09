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
from app.utils.navigation import answer_with_navigation
from app.utils.temporary_screens import refresh_temporary_message, schedule_temporary_message
from app.utils.transaction_format import project_suffix
from app.utils.currency import family_currency, format_money
from app.i18n import category_label, family_language, t

router = Router()

LIMIT = 20


def format_transaction(transaction, currency_code: str = "EUR", language: str = "ru") -> str:

    sign = "+" if transaction.type == "income" else "-"

    amount = abs(transaction.amount)

    amount_text = f"{sign}{format_money(amount, currency_code)}"

    if transaction.is_recurring:
        amount_text += "/мес"

    base_icon = (
        "💰"
        if transaction.type == "income"
        else escape(category_label(language, transaction.category).split()[0])
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
        f"{project_suffix(transaction)}"
    )


async def build_history_text(family_id: int, offset: int = 0, currency_code: str = "EUR", language: str = "ru"):

    total = await get_transactions_count(family_id)

    transactions = await get_last_transactions(
        family_id=family_id,
        limit=LIMIT,
        offset=offset,
    )

    if not transactions:
        return t(language, "history.empty")

    text = (
        f"<b>{t(language, 'history.title')}</b>\n\n"
    )

    for transaction in transactions:
        text += (
            format_transaction(transaction, currency_code, language)
            + "\n"
        )

    shown = min(
        offset + LIMIT,
        total,
    )

    text += (
        f"\n<b>{t(language, 'common.shown', shown=shown, total=total)}</b>"
    )

    return text

@router.message(Command("history"))
async def history(message: Message):
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type,
        telegram_id=message.from_user.id,
    )
    total = await get_transactions_count(family.id)

    sent_message = await answer_with_navigation(
        message,
        await build_history_text(family.id, 0, family_currency(family), family_language(family)),
        inline_markup=pagination_keyboard(
            prefix="history",
            offset=0,
            total=total,
            limit=LIMIT,
            language=family_language(family),
        ),
    )
    schedule_temporary_message(sent_message, ttl=family.temporary_screen_ttl)


@router.callback_query(
    F.data.startswith("history:")
)
async def history_page(
    callback: CallbackQuery,
):

    offset = int(
        callback.data.split(":")[1]
    )

    family = await require_family_for_chat(
        callback.message.chat.id, chat_type=callback.message.chat.type,
        telegram_id=callback.from_user.id,
    )
    total = await get_transactions_count(family.id)

    await callback.message.edit_text(
        await build_history_text(family.id, offset, family_currency(family), family_language(family)),
        reply_markup=pagination_keyboard(
            prefix="history",
            offset=offset,
            total=total,
            limit=LIMIT,
            language=family_language(family),
        ),
    )

    refresh_temporary_message(callback.message, ttl=family.temporary_screen_ttl)
    await callback.answer()
