from aiogram import F, Router
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
)
from app.utils.fsm import cancel_state

router = Router()


recurring_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="➕ Добавить шаблон"),
            KeyboardButton(text="📋 Список"),
        ],
        [
            KeyboardButton(text="🗑 Удалить"),
            KeyboardButton(text="✏️ Изменить"),
        ],
        [
            KeyboardButton(text="📅 Создать расходы месяца"),
        ],
        [
            KeyboardButton(text="❌ Отмена"),
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


@router.message(F.text == "❌ Отмена")
async def cancel(message: Message, state: FSMContext):

    await cancel_state(state)

    await message.answer(
        "Действие отменено.",
        reply_markup=recurring_keyboard,
    )


@router.message(F.text == "➕ Добавить шаблон")
async def add_template(message: Message, state: FSMContext):

    await cancel_state(state)

    await state.set_state(RecurringState.waiting_for_payment)

    await message.answer(
        "<b>Новый шаблон</b>\n\n"
        "Введите одной строкой.\n\n"
        "<pre>Интернет 50</pre>\n"
        "<pre>Аренда 1150</pre>\n"
        "<pre>YouTube 24</pre>",
        reply_markup=recurring_keyboard,
    )


@router.message(
    RecurringState.waiting_for_payment,
    F.text.regexp(r".*\d+([.,]\d+)?$")
)
async def save_template(message: Message, state: FSMContext):

    payment = await create_payment(
        message.text,
        message.from_user.id,
    )

    if payment is None:

        await message.answer(
            "❌ Не удалось распознать.\nПопробуйте еще раз.",
            reply_markup=recurring_keyboard,
        )
        return

    await cancel_state(state)

    await message.answer(
        "✅ Шаблон сохранён.\n\n"
        f"{payment.title} — {payment.amount:.2f} €",
        reply_markup=recurring_keyboard,
    )


@router.message(F.text == "📋 Список")
async def payment_list(message: Message, state: FSMContext):

    await cancel_state(state)

    payments = await list_payments(message.from_user.id)

    if not payments:

        await message.answer(
            "Пока нет ни одного шаблона.",
            reply_markup=recurring_keyboard,
        )
        return

    text = "<b>🔁 Регулярные платежи</b>\n\n"

    total = 0

    for i, payment in enumerate(payments, start=1):

        total += payment.amount

        text += (
            f"{i}. {payment.title}"
            f" — {payment.amount:.2f} €\n"
        )

    text += "\n"
    text += f"💰 Всего шаблонов: {len(payments)}\n"
    text += f"💶 Сумма: {total:.2f} €"

    await message.answer(
        text,
        reply_markup=recurring_keyboard,
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
            f"{payment.title} — {payment.amount:.2f} €",
            reply_markup=delete_keyboard(payment.id),
        )


@router.callback_query(F.data.startswith("rec_delete:"))
async def delete_template_callback(callback: CallbackQuery):

    payment_id = int(callback.data.split(":", maxsplit=1)[1])
    deleted = await remove_payment(payment_id, callback.from_user.id)

    if deleted:
        await callback.message.edit_reply_markup(reply_markup=None)
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
            f"ID {payment.id}: {payment.title}"
            f" — {payment.amount:.2f} €\n"
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
        f"{payment.title} — {payment.amount:.2f} €",
        reply_markup=recurring_keyboard,
    )


@router.message(F.text == "📅 Создать расходы месяца")
async def create_month(message: Message, state: FSMContext):

    await cancel_state(state)

    created = await create_month_transactions(message.from_user.id)

    await message.answer(
        "✅ Регулярные расходы созданы.\n\n"
        f"Добавлено операций: {created}",
        reply_markup=recurring_keyboard,
    )
