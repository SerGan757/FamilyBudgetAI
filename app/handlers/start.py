from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.handlers.user_states import RegistrationState
from app.keyboards.main_menu import main_menu
from app.services.user_service import (
    create_user,
    get_user_by_telegram_id,
)

router = Router()


WELCOME_TEXT = """
👋 <b>Добро пожаловать в Family Budget AI</b>

Ваш семейный помощник по учету финансов.

<b>Как добавить расход</b>

<pre>
Кофе 3.50
Lidl 42.80
</pre>

<b>Как добавить доход</b>

<pre>
 Зарплата +2300
+150 Возврат
</pre>

════════════════════

<b>Возможности</b>

🛒 Расходы
💰 Доходы
📊 Статистика
📖 История
🔁 Регулярные платежи
"""


@router.message(Command("start"))
async def cmd_start(
    message: Message,
    state: FSMContext,
):
    print("START:", message.from_user.id, message.text)

    telegram_id = message.from_user.id

    user = await get_user_by_telegram_id(
        telegram_id
    )

    if user:

        await state.clear()

        await message.answer(
            f"👋 С возвращением, <b>{user.name}</b>!"
        )

        await message.answer(
            WELCOME_TEXT,
            reply_markup=main_menu,
        )

        return

    await state.set_state(
        RegistrationState.waiting_for_name
    )

    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "Как тебя зовут?"
    )


@router.message(RegistrationState.waiting_for_name)
async def registration_name(
    message: Message,
    state: FSMContext,
):

    if message.text is None:
        return

    name = message.text.strip()

    if len(name) < 2:

        await message.answer(
            "Введите корректное имя."
        )
        return

    await create_user(
        telegram_id=message.from_user.id,
        name=name,
    )

    await state.clear()

    await message.answer(
        f"✅ Рад познакомиться, <b>{name}</b>!"
    )

    await message.answer(
        WELCOME_TEXT,
        reply_markup=main_menu,
    )