from datetime import date
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup

from app.handlers.recurring_states import RecurringState
from app.i18n import all_texts, family_language, month_name, t
from app.keyboards.main_menu import main_menu_keyboard
from app.keyboards.recurring_inline import delete_keyboard
from app.services.family_context_service import require_family_for_chat
from app.services.recurring_manager import (
    create_month_transactions,
    create_payment,
    get_month_recurring_transactions,
    list_payments,
    remove_payment,
    update_payment,
)
from app.services.user_service import get_user_by_telegram_id
from app.utils.currency import family_currency, format_money, format_signed_money
from app.utils.fsm import cancel_state

router = Router()


def recurring_keyboard_for(language: str = "ru") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(language, "recurring.add")), KeyboardButton(text=t(language, "recurring.edit"))],
            [KeyboardButton(text=t(language, "recurring.delete")), KeyboardButton(text=t(language, "recurring.payments"))],
            [KeyboardButton(text=t(language, "recurring.create_month")), KeyboardButton(text=t(language, "menu.back"))],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


recurring_keyboard = recurring_keyboard_for()
RECURRING_MENU_TEXTS = set().union(*(
    all_texts(key) for key in (
        "recurring.add", "recurring.edit", "recurring.delete",
        "recurring.payments", "recurring.create_month", "menu.back",
    )
))


async def _validate_recurring_fsm_family(message: Message, state: FSMContext):
    data = await state.get_data()
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type,
        telegram_id=message.from_user.id,
    )
    if data.get("recurring_chat_id") != message.chat.id or data.get("recurring_family_id") != family.id:
        language = family_language(family)
        await state.clear()
        await message.answer(t(language, "recurring.cross_chat"), reply_markup=recurring_keyboard_for(language))
        return None
    return family


async def recurring_menu(message: Message):
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type, telegram_id=message.from_user.id,
    )
    language = family_language(family)
    await message.answer(
        f"<b>🔁 {t(language, 'recurring.title')}</b>",
        reply_markup=recurring_keyboard_for(language),
        parse_mode="HTML",
    )


@router.message(F.text.in_(all_texts("menu.back")))
async def back_to_main(message: Message, state: FSMContext):
    await cancel_state(state)
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type, telegram_id=message.from_user.id,
    )
    language = family_language(family)
    await message.answer(t(language, "menu.title"), reply_markup=main_menu_keyboard(language))


@router.message(F.text.in_(all_texts("recurring.add")))
async def add_template(message: Message, state: FSMContext):
    await cancel_state(state)
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type, telegram_id=message.from_user.id,
    )
    language = family_language(family)
    currency = family_currency(family)
    monthly = t(language, "common.monthly")
    payments = await list_payments(family.id)
    expense_rows, income_rows = [], []
    expense_total = income_total = 0.0
    for payment in payments:
        amount = format_money(payment.amount, currency)
        if payment.type == "income":
            income_total += payment.amount
            income_rows.append(f"{len(income_rows) + 1}. {escape(payment.title)} — +{amount}/{monthly}")
        else:
            expense_total += payment.amount
            expense_rows.append(f"{len(expense_rows) + 1}. {escape(payment.title)} — {amount}/{monthly}")

    text = f"<b>🔁 {t(language, 'recurring.current')}</b>\n\n"
    if expense_rows:
        text += f"<b>💸 {t(language, 'recurring.expenses')}</b>\n\n" + "\n".join(expense_rows) + "\n"
    if income_rows:
        text += f"\n━━━━━━━━━━━━━━━━━━\n\n<b>💰 {t(language, 'recurring.income')}</b>\n\n" + "\n".join(income_rows) + "\n"
    if payments:
        text += (
            f"\n━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>💸 {t(language, 'recurring.expenses')}: {format_money(expense_total, currency)}/{monthly} ({len(expense_rows)})</b>\n"
            f"<b>💰 {t(language, 'recurring.income')}: {format_money(income_total, currency)}/{monthly} ({len(income_rows)})</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n\n<b>💶 {t(language, 'recurring.balance')}: "
            f"{format_signed_money(income_total - expense_total, currency)}/{monthly}</b>\n\n"
        )
    else:
        text += f"{t(language, 'recurring.empty')}\n\n"
    text += f"<b>{t(language, 'recurring.enter_new')}</b>\n\n<pre>Internet 50</pre>\n<pre>Netflix 15</pre>\n<pre>Rent 1300</pre>"
    await state.update_data(recurring_family_id=family.id, recurring_chat_id=message.chat.id)
    await state.set_state(RecurringState.waiting_for_payment)
    await message.answer(text, reply_markup=recurring_keyboard_for(language), parse_mode="HTML")


@router.message(RecurringState.waiting_for_payment, ~F.text.in_(RECURRING_MENU_TEXTS))
async def save_template(message: Message, state: FSMContext):
    family = await _validate_recurring_fsm_family(message, state)
    if family is None:
        return
    language = family_language(family)
    payment = await create_payment(family.id, message.text)
    if payment is None:
        await message.answer(
            t(language, "recurring.invalid_template"),
            reply_markup=recurring_keyboard_for(language), parse_mode="HTML",
        )
        return
    await cancel_state(state)
    await message.answer(
        f"{t(language, 'recurring.saved')}\n\n{escape(payment.title)} — "
        f"{format_money(payment.amount, family_currency(family))}/{t(language, 'common.monthly')}",
        reply_markup=recurring_keyboard_for(language), parse_mode="HTML",
    )


@router.message(F.text.in_(all_texts("recurring.payments")))
async def month_recurring(message: Message, state: FSMContext):
    await cancel_state(state)
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type, telegram_id=message.from_user.id,
    )
    language = family_language(family)
    currency = family_currency(family)
    monthly = t(language, "common.monthly")
    transactions = await get_month_recurring_transactions(family.id)
    today = date.today()
    text = f"<b>📅 {t(language, 'recurring.month_title')}</b>\n{month_name(language, today.month)} {today.year}\n\n"
    if not transactions:
        await message.answer(
            text + t(language, "recurring.month_empty"),
            reply_markup=recurring_keyboard_for(language), parse_mode="HTML",
        )
        return

    expense_rows, income_rows = [], []
    expense_total = income_total = 0.0
    for transaction in transactions:
        author = escape(transaction.user.name) if getattr(transaction, "user", None) else ""
        amount = format_money(transaction.amount, currency)
        if transaction.type == "income":
            income_total += transaction.amount
            income_rows.append(f"🔁 💰 {escape(transaction.title)} +{amount}/{monthly} {author}")
        else:
            expense_total += transaction.amount
            expense_rows.append(f"🔁 {escape(transaction.title)} -{amount}/{monthly} {author}")
    if expense_rows:
        text += f"<b>💸 {t(language, 'recurring.expenses')}</b>\n\n" + "\n".join(expense_rows)
    if income_rows:
        text += f"\n\n━━━━━━━━━━━━━━━━━━\n\n<b>💰 {t(language, 'recurring.income')}</b>\n\n" + "\n".join(income_rows)
    text += (
        f"\n\n━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>💸 {t(language, 'recurring.expenses')}: {format_money(expense_total, currency)}/{monthly} ({len(expense_rows)})</b>\n"
        f"<b>💰 {t(language, 'recurring.income')}: {format_money(income_total, currency)}/{monthly} ({len(income_rows)})</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n\n<b>💶 {t(language, 'recurring.balance')}: "
        f"{format_signed_money(income_total - expense_total, currency)}/{monthly}</b>"
    )
    await message.answer(text, reply_markup=recurring_keyboard_for(language), parse_mode="HTML")


@router.message(F.text.in_(all_texts("recurring.delete")))
async def delete_template(message: Message, state: FSMContext):
    await cancel_state(state)
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type, telegram_id=message.from_user.id,
    )
    language = family_language(family)
    payments = await list_payments(family.id)
    if not payments:
        await message.answer(t(language, "recurring.none"), reply_markup=recurring_keyboard_for(language))
        return
    for payment in payments:
        await message.answer(
            f"{escape(payment.title)} — {format_money(payment.amount, family_currency(family))}/{t(language, 'common.monthly')}",
            reply_markup=delete_keyboard(payment.id, language), parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("rec_delete:"))
async def delete_template_callback(callback: CallbackQuery):
    payment_id = int(callback.data.split(":", maxsplit=1)[1])
    family = await require_family_for_chat(
        callback.message.chat.id, chat_type=callback.message.chat.type, telegram_id=callback.from_user.id,
    )
    language = family_language(family)
    if await remove_payment(family.id, payment_id):
        await callback.message.edit_text(t(language, "recurring.deleted"))
        await callback.answer(t(language, "recurring.deleted"))
        return
    await callback.answer(t(language, "recurring.not_found"), show_alert=True)


@router.message(F.text.in_(all_texts("recurring.edit")))
async def edit_template(message: Message, state: FSMContext):
    await cancel_state(state)
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type, telegram_id=message.from_user.id,
    )
    language = family_language(family)
    payments = await list_payments(family.id)
    if not payments:
        await message.answer(t(language, "recurring.none"), reply_markup=recurring_keyboard_for(language))
        return
    text = f"<b>{t(language, 'recurring.edit_title')}</b>\n\n"
    for payment in payments:
        text += f"ID {payment.id}: {escape(payment.title)} — {format_money(payment.amount, family_currency(family))}/{t(language, 'common.monthly')}\n"
    text += f"\n{t(language, 'recurring.edit_instruction')}\n\n<pre>12 Internet 55</pre>"
    await state.update_data(recurring_family_id=family.id, recurring_chat_id=message.chat.id)
    await state.set_state(RecurringState.waiting_for_edit_payment)
    await message.answer(text, reply_markup=recurring_keyboard_for(language), parse_mode="HTML")


@router.message(RecurringState.waiting_for_edit_payment)
async def save_edited_template(message: Message, state: FSMContext):
    family = await _validate_recurring_fsm_family(message, state)
    if family is None:
        return
    language = family_language(family)
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2 or not parts[0].isdigit():
        await message.answer(t(language, "recurring.edit_invalid"), reply_markup=recurring_keyboard_for(language))
        return
    payment = await update_payment(family.id, int(parts[0]), parts[1])
    if payment is None:
        await message.answer(t(language, "recurring.edit_failed"), reply_markup=recurring_keyboard_for(language))
        return
    await cancel_state(state)
    await message.answer(
        f"{t(language, 'recurring.edited')}\n\n{escape(payment.title)} — "
        f"{format_money(payment.amount, family_currency(family))}/{t(language, 'common.monthly')}",
        reply_markup=recurring_keyboard_for(language), parse_mode="HTML",
    )


@router.message(F.text.in_(all_texts("recurring.create_month")))
async def create_month(message: Message, state: FSMContext):
    await cancel_state(state)
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type, telegram_id=message.from_user.id,
    )
    language = family_language(family)
    user = await get_user_by_telegram_id(message.from_user.id)
    if user is None or user.family_id != family.id:
        await message.answer(t(language, "recurring.user_not_registered"), reply_markup=recurring_keyboard_for(language))
        return
    result = await create_month_transactions(family.id, user.id)
    today = date.today()
    text = (
        f"✅ <b>{t(language, 'recurring.month_operations')} — {month_name(language, today.month)} {today.year}</b>\n\n"
        f"➕ {t(language, 'recurring.created')}: {result['created']}\n"
        f"✏️ {t(language, 'recurring.updated_count')}: {result['updated']}\n"
        f"✓ {t(language, 'recurring.unchanged')}: {result['unchanged']}"
    )
    if result["details"]:
        text += "\n\n"
        for item in result["details"]:
            icon = "➕" if item["status"] == "created" else "✏️" if item["status"] == "updated" else "✓"
            sign = "+" if item.get("type") == "income" else "-"
            text += (
                f"{icon} {escape(item['title'])} — {sign}{format_money(item['amount'], family_currency(family))}/"
                f"{t(language, 'common.monthly')}\n"
            )
    await message.answer(text, reply_markup=recurring_keyboard_for(language), parse_mode="HTML")
