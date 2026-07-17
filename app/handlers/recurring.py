from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from app.handlers.recurring_states import RecurringState
from app.keyboards.main_menu import main_menu
from app.services.recurring_manager import (
    create_payment,
    list_payments,
    create_month_transactions,
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

    payment = await create_payment(message.text)

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

    payments = await list_payments()

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

    await message.answer(
        "🚧 Следующий этап — удаление шаблонов.",
        reply_markup=recurring_keyboard,
    )


@router.message(F.text == "✏️ Изменить")
async def edit_template(message: Message, state: FSMContext):

    await cancel_state(state)

    await message.answer(
        "🚧 Следующий этап — изменение шаблонов.",
        reply_markup=recurring_keyboard,
    )


@router.message(F.text == "📅 Создать расходы месяца")
async def create_month(message: Message, state: FSMContext):

    await cancel_state(state)

    created = await create_month_transactions()

    await message.answer(
        "✅ Регулярные расходы созданы.\n\n"
        f"Добавлено операций: {created}",
        reply_markup=recurring_keyboard,
    )