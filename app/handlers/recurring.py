from aiogram import F, Router
from html import escape
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup

from app.handlers.recurring_states import RecurringState
from app.keyboards.main_menu import main_menu_keyboard
from app.keyboards.recurring_inline import delete_keyboard
from app.services.recurring_manager import (
    create_payment,
    list_payments,
    create_month_transactions,
    remove_payment,
    update_payment,
    get_month_recurring_transactions,
)
from app.services.family_context_service import require_family_for_chat
from app.services.user_service import get_user_by_telegram_id
from app.utils.fsm import cancel_state
from app.utils.currency import family_currency, format_money, format_signed_money
from app.i18n import all_texts, family_language, t

router = Router()


def recurring_keyboard_for(language: str = "ru") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [
            KeyboardButton(text=t(language, "recurring.add")),
            KeyboardButton(text=t(language, "recurring.edit")),
        ],
        [
            KeyboardButton(text=t(language, "recurring.delete")),
            KeyboardButton(text=t(language, "recurring.payments")),
        ],
        [
            KeyboardButton(text=t(language, "recurring.create_month")),
            KeyboardButton(text=t(language, "menu.back")),
        ],
    ], resize_keyboard=True, is_persistent=True)

recurring_keyboard = recurring_keyboard_for()


async def _validate_recurring_fsm_family(
    message: Message,
    state: FSMContext,
):
    """Ensure an add/edit scenario cannot be continued from another chat."""
    data = await state.get_data()
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type,
        telegram_id=message.from_user.id,
    )
    if (
        data.get("recurring_chat_id") != message.chat.id
        or data.get("recurring_family_id") != family.id
    ):
        await state.clear()
        await message.answer(
            "Сценарий был начат в другом чате. Начните действие заново.",
            reply_markup=recurring_keyboard,
        )
        return None
    return family

async def recurring_menu(message: Message):

    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type,
        telegram_id=message.from_user.id,
    )

    await message.answer(
        f"<b>🔁 {t(family_language(family), 'recurring.title')}</b>",
        reply_markup=recurring_keyboard_for(family_language(family)),
    )


@router.message(F.text.in_(all_texts("menu.back")))
async def back_to_main(message: Message, state: FSMContext):

    await cancel_state(state)

    family = await require_family_for_chat(message.chat.id, chat_type=message.chat.type, telegram_id=message.from_user.id)
    await message.answer(t(family_language(family), "menu.title"), reply_markup=main_menu_keyboard(family_language(family)))


@router.message(F.text.in_(all_texts("recurring.add")))
async def add_template(message: Message, state: FSMContext):

    await cancel_state(state)
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type,
        telegram_id=message.from_user.id,
    )

    payments = await list_payments(family.id)
    expense_text = ""
    income_text = ""

    expense_total = 0
    income_total = 0

    expense_count = 0
    income_count = 0

    text = "<b>🔁 Текущие шаблоны</b>\n\n"

    
    if payments:

        exp = 1
        inc = 1

        for payment in payments:

            if payment.type == "income":

                income_total += payment.amount
                income_count += 1

                income_text += (
                    f"{inc}. {escape(payment.title)}"
                    f" — +{format_money(payment.amount, family_currency(family))}/мес\n"
                )

                inc += 1

            else:

                expense_total += payment.amount
                expense_count += 1

                expense_text += (
                    f"{exp}. {escape(payment.title)}"
                    f" — {format_money(payment.amount, family_currency(family))}/мес\n"
                )

                exp += 1

        if expense_text:

            text += "<b>💸 Расходы</b>\n\n"
            text += expense_text

        if income_text:

            text += "\n━━━━━━━━━━━━━━━━━━\n\n"
            text += "<b>💰 Доходы</b>\n\n"
            text += income_text

        text += (
            "\n━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>💸 Расходы: {format_money(expense_total, family_currency(family))}/мес ({expense_count})</b>\n"
            f"<b>💰 Доходы: {format_money(income_total, family_currency(family))}/мес ({income_count})</b>\n\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>💶 Баланс: "
            f"{format_signed_money(income_total-expense_total, family_currency(family))}/мес</b>\n\n"
        )

    else:

        text += "Пока шаблонов нет.\n\n"

    text += (
        "<b>Введите новый шаблон:</b>\n\n"
        "<pre>Интернет 50</pre>\n"
        "<pre>Netflix 15</pre>\n"
        "<pre>Аренда 1300</pre>"
    )

    await state.update_data(
        recurring_family_id=family.id,
        recurring_chat_id=message.chat.id,
    )
    await state.set_state(RecurringState.waiting_for_payment)

    await message.answer(
        text,
        reply_markup=recurring_keyboard,
        parse_mode="HTML",
    )


@router.message(
    RecurringState.waiting_for_payment,
    ~F.text.in_(
        {
            "➕ Добавить шаблон",
            "✏️ Изменить",
            "🗑 Удалить",
            "📅 Платежи",
            "📅 Создать операции месяца",
            "⬅️ Главное меню",
        }
    ),
)
async def save_template(message: Message, state: FSMContext):

    family = await _validate_recurring_fsm_family(message, state)
    if family is None:
        return

    payment = await create_payment(
        family.id,
        message.text,
    )

    if payment is None:
        await message.answer(
            "❌ Не удалось распознать.\n"
            "Введите шаблон в формате:\n\n"
            "<pre>Интернет 50</pre>",
            reply_markup=recurring_keyboard,
            parse_mode="HTML",
        )
        return

    await cancel_state(state)

    await message.answer(
        "✅ Шаблон сохранён.\n\n"
        f"{escape(payment.title)} — {format_money(payment.amount, family_currency(family))}/мес",
        reply_markup=recurring_keyboard,
    )


@router.message(F.text.in_(all_texts("recurring.payments")))
async def month_recurring(message: Message, state: FSMContext):

    from datetime import date

    await cancel_state(state)
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type,
        telegram_id=message.from_user.id,
    )

    transactions = await get_month_recurring_transactions(
        family.id
    )

    months = [
        "",
        "Январь",
        "Февраль",
        "Март",
        "Апрель",
        "Май",
        "Июнь",
        "Июль",
        "Август",
        "Сентябрь",
        "Октябрь",
        "Ноябрь",
        "Декабрь",
    ]

    today = date.today()

    text = (
        f"<b>📅 Регулярные платежи</b>\n"
        f"{months[today.month]} {today.year}\n\n"
    )

    if not transactions:

        text += (
            "Регулярные платежи "
            "за этот месяц отсутствуют."
        )

        await message.answer(
            text,
            reply_markup=recurring_keyboard,
            parse_mode="HTML",
        )
        return

    expense_text = ""
    income_text = ""

    expense_total = 0
    income_total = 0

    expense_count = 0
    income_count = 0

    for transaction in transactions:

        author = (
            escape(transaction.user.name)
            if getattr(transaction, "user", None)
            else ""
        )

        if transaction.type == "income":

            income_total += transaction.amount
            income_count += 1

            income_text += (
                f"🔁 💰 {escape(transaction.title)} "
                f"+{format_money(transaction.amount, family_currency(family))}/мес "
                f"{author}\n"
            )

        else:

            expense_total += transaction.amount
            expense_count += 1

            expense_text += (
                f"🔁 {escape(transaction.title)} "
                f"-{format_money(transaction.amount, family_currency(family))}/мес "
                f"{author}\n"
            )

    if expense_text:

        text += "<b>💸 Расходы</b>\n\n"
        text += expense_text

    if income_text:

        text += "\n━━━━━━━━━━━━━━━━━━\n\n"
        text += "<b>💰 Доходы</b>\n\n"
        text += income_text

    text += (
        "\n━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>💸 Расходы: {format_money(expense_total, family_currency(family))}/мес ({expense_count})</b>\n"
        f"<b>💰 Доходы: {format_money(income_total, family_currency(family))}/мес ({income_count})</b>\n\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>💶 Баланс: "
        f"{format_signed_money(income_total-expense_total, family_currency(family))}/мес</b>"
    )

    await message.answer(
        text,
        reply_markup=recurring_keyboard,
        parse_mode="HTML",
    )


@router.message(F.text.in_(all_texts("recurring.delete")))
async def delete_template(message: Message, state: FSMContext):

    await cancel_state(state)
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type,
        telegram_id=message.from_user.id,
    )

    payments = await list_payments(family.id)

    if not payments:
        await message.answer(
            "Пока нет ни одного шаблона.",
            reply_markup=recurring_keyboard,
        )
        return

    for payment in payments:
        await message.answer(
            f"{payment.title} — {format_money(payment.amount, family_currency(family))}/мес",
            reply_markup=delete_keyboard(payment.id),
        )


@router.callback_query(F.data.startswith("rec_delete:"))
async def delete_template_callback(callback: CallbackQuery):

    payment_id = int(callback.data.split(":", maxsplit=1)[1])
    family = await require_family_for_chat(
        callback.message.chat.id, chat_type=callback.message.chat.type,
        telegram_id=callback.from_user.id,
    )
    deleted = await remove_payment(family.id, payment_id)

    if deleted:
        await callback.message.edit_text("✅ Шаблон удалён")
        await callback.answer("Шаблон удалён")
        return

    await callback.answer("Шаблон не найден", show_alert=True)


@router.message(F.text.in_(all_texts("recurring.edit")))
async def edit_template(message: Message, state: FSMContext):

    await cancel_state(state)
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type,
        telegram_id=message.from_user.id,
    )

    payments = await list_payments(family.id)

    if not payments:
        await message.answer(
            "Пока нет ни одного шаблона.",
            reply_markup=recurring_keyboard,
        )
        return

    text = "<b>Изменение шаблона</b>\n\n"

    for payment in payments:
        text += (
            f"ID {payment.id}: {escape(payment.title)}"
            f" — {format_money(payment.amount, family_currency(family))}/мес\n"
        )

    text += "\nВведите ID и новые данные.\n\n<pre>12 Интернет 55</pre>"

    await state.update_data(
        recurring_family_id=family.id,
        recurring_chat_id=message.chat.id,
    )
    await state.set_state(RecurringState.waiting_for_edit_payment)

    await message.answer(
        text,
        reply_markup=recurring_keyboard,
    )


@router.message(RecurringState.waiting_for_edit_payment)
async def save_edited_template(message: Message, state: FSMContext):

    family = await _validate_recurring_fsm_family(message, state)
    if family is None:
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) != 2 or not parts[0].isdigit():
        await message.answer(
            "Введите ID и новые данные одной строкой.",
            reply_markup=recurring_keyboard,
        )
        return

    payment = await update_payment(
        family.id,
        int(parts[0]),
        parts[1],
    )

    if payment is None:
        await message.answer(
            "Не удалось изменить шаблон. Проверьте ID и данные.",
            reply_markup=recurring_keyboard,
        )
        return

    await cancel_state(state)

    await message.answer(
        "✅ Шаблон изменён.\n\n"
        f"{escape(payment.title)} — {format_money(payment.amount, family_currency(family))}/мес",
        reply_markup=recurring_keyboard,
    )


@router.message(F.text.in_(all_texts("recurring.create_month")))
async def create_month(message: Message, state: FSMContext):

    from datetime import date

    await cancel_state(state)
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type,
        telegram_id=message.from_user.id,
    )
    user = await get_user_by_telegram_id(message.from_user.id)
    if user is None or user.family_id != family.id:
        await message.answer(
            "⚠️ Пользователь не зарегистрирован в этой семье.",
            reply_markup=recurring_keyboard,
        )
        return

    result = await create_month_transactions(family.id, user.id)

    months = [
        "",
        "Январь",
        "Февраль",
        "Март",
        "Апрель",
        "Май",
        "Июнь",
        "Июль",
        "Август",
        "Сентябрь",
        "Октябрь",
        "Ноябрь",
        "Декабрь",
    ]

    today = date.today()

    text = (
        f"✅ <b>Регулярные операции — "
        f"{months[today.month]} {today.year}</b>\n\n"
        f"➕ Создано: {result['created']}\n"
        f"✏️ Обновлено: {result['updated']}\n"
        f"✓ Без изменений: {result['unchanged']}"
    )

    if result["details"]:

        text += "\n\n"

        for item in result["details"]:

            if item["status"] == "created":
                icon = "➕"
            elif item["status"] == "updated":
                icon = "✏️"
            else:
                icon = "✓"

            sign = "+" if item.get("type") == "income" else "-"

            text += (
                f"{icon} {escape(item['title'])} — "
                f"{sign}{format_money(item['amount'], family_currency(family))}/мес\n"
            )

    await message.answer(
        text,
        reply_markup=recurring_keyboard,
        parse_mode="HTML",
    )
