from aiogram import F, Router
from html import escape
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup

from app.handlers.recurring_states import RecurringState
from app.keyboards.main_menu import main_menu
from app.keyboards.recurring_inline import delete_keyboard
from app.services.recurring_manager import (
    create_payment,
    list_payments,
    create_month_transactions,
    remove_payment,
    update_payment,
    get_month_recurring_transactions,
)
from app.utils.fsm import cancel_state

router = Router()


recurring_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="➕ Добавить шаблон"),
            KeyboardButton(text="✏️ Изменить"),
        ],
        [
            KeyboardButton(text="🗑 Удалить"),
            KeyboardButton(text="📅 Платежи"),
        ],
        [
            KeyboardButton(text="📅 Создать операции месяца"),
            KeyboardButton(text="⬅️ Главное меню"),
        ],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

async def recurring_menu(message: Message):

    await message.answer(
        "<b>🔁 Регулярные платежи</b>\n\n"
        "Выберите действие.",
        reply_markup=recurring_keyboard,
    )


@router.message(F.text == "⬅️ Главное меню")
async def back_to_main(message: Message, state: FSMContext):

    await cancel_state(state)

    await message.answer(
        "Главное меню",
        reply_markup=main_menu,
    )


@router.message(F.text == "➕ Добавить шаблон")
async def add_template(message: Message, state: FSMContext):

    await cancel_state(state)

    payments = await list_payments(message.from_user.id)
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
                    f" — +{payment.amount:.2f} €/мес\n"
                )

                inc += 1

            else:

                expense_total += payment.amount
                expense_count += 1

                expense_text += (
                    f"{exp}. {escape(payment.title)}"
                    f" — {payment.amount:.2f} €/мес\n"
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
            f"<b>💸 Расходы: {expense_total:.2f} €/мес ({expense_count})</b>\n"
            f"<b>💰 Доходы: {income_total:.2f} €/мес ({income_count})</b>\n\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>💶 Баланс: "
            f"{income_total-expense_total:+.2f} €/мес</b>\n\n"
        )

    else:

        text += "Пока шаблонов нет.\n\n"

    text += (
        "<b>Введите новый шаблон:</b>\n\n"
        "<pre>Интернет 50</pre>\n"
        "<pre>Netflix 15</pre>\n"
        "<pre>Аренда 1300</pre>"
    )

    await state.set_state(
        RecurringState.waiting_for_payment
    )

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

    payment = await create_payment(
        message.text,
        message.from_user.id,
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
        f"{escape(payment.title)} — {payment.amount:.2f} €/мес",
        reply_markup=recurring_keyboard,
    )


@router.message(F.text == "📅 Платежи")
async def month_recurring(message: Message, state: FSMContext):

    from datetime import date

    await cancel_state(state)

    transactions = await get_month_recurring_transactions(
        message.from_user.id
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
                f"+{transaction.amount:.2f} €/мес "
                f"{author}\n"
            )

        else:

            expense_total += transaction.amount
            expense_count += 1

            expense_text += (
                f"🔁 {escape(transaction.title)} "
                f"-{transaction.amount:.2f} €/мес "
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
        f"<b>💸 Расходы: {expense_total:.2f} €/мес ({expense_count})</b>\n"
        f"<b>💰 Доходы: {income_total:.2f} €/мес ({income_count})</b>\n\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>💶 Баланс: "
        f"{income_total-expense_total:+.2f} €/мес</b>"
    )

    await message.answer(
        text,
        reply_markup=recurring_keyboard,
        parse_mode="HTML",
    )


@router.message(F.text == "🗑 Удалить")
async def delete_template(message: Message, state: FSMContext):

    await cancel_state(state)

    payments = await list_payments(message.from_user.id)

    if not payments:
        await message.answer(
            "Пока нет ни одного шаблона.",
            reply_markup=recurring_keyboard,
        )
        return

    for payment in payments:
        await message.answer(
            f"{payment.title} — {payment.amount:.2f} €/мес",
            reply_markup=delete_keyboard(payment.id),
        )


@router.callback_query(F.data.startswith("rec_delete:"))
async def delete_template_callback(callback: CallbackQuery):

    payment_id = int(callback.data.split(":", maxsplit=1)[1])
    deleted = await remove_payment(payment_id, callback.from_user.id)

    if deleted:
        await callback.message.edit_text("✅ Шаблон удалён")
        await callback.answer("Шаблон удалён")
        return

    await callback.answer("Шаблон не найден", show_alert=True)


@router.message(F.text == "✏️ Изменить")
async def edit_template(message: Message, state: FSMContext):

    await cancel_state(state)

    payments = await list_payments(message.from_user.id)

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
            f" — {payment.amount:.2f} €/мес\n"
        )

    text += "\nВведите ID и новые данные.\n\n<pre>12 Интернет 55</pre>"

    await state.set_state(RecurringState.waiting_for_edit_payment)

    await message.answer(
        text,
        reply_markup=recurring_keyboard,
    )


@router.message(RecurringState.waiting_for_edit_payment)
async def save_edited_template(message: Message, state: FSMContext):

    parts = message.text.split(maxsplit=1)

    if len(parts) != 2 or not parts[0].isdigit():
        await message.answer(
            "Введите ID и новые данные одной строкой.",
            reply_markup=recurring_keyboard,
        )
        return

    payment = await update_payment(
        int(parts[0]),
        parts[1],
        message.from_user.id,
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
        f"{escape(payment.title)} — {payment.amount:.2f} €/мес",
        reply_markup=recurring_keyboard,
    )


@router.message(F.text == "📅 Создать операции месяца")
async def create_month(message: Message, state: FSMContext):

    from datetime import date

    await cancel_state(state)

    result = await create_month_transactions(message.from_user.id)

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
                f"{sign}{item['amount']:.2f} €/мес\n"
            )

    await message.answer(
        text,
        reply_markup=recurring_keyboard,
        parse_mode="HTML",
    )
