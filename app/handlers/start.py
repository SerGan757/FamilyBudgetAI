from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.handlers.user_states import RegistrationState
from app.keyboards.main_menu import main_menu
from app.services.family_context_service import (
    FamilyContextConflictError,
    FamilyContextNotFoundError,
    get_or_create_family_for_chat,
    require_family_for_chat,
)
from app.services.user_service import (
    create_user,
    get_user_by_telegram_id,
)
from app.i18n import normalize_telegram_language

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
    chat_id = message.chat.id
    chat_title = message.chat.title or f"Личный бюджет {message.from_user.full_name}"

    try:
        family = await get_or_create_family_for_chat(
            chat_id, chat_title,
            initial_language=normalize_telegram_language(getattr(message.from_user, "language_code", None)),
        )
    except FamilyContextConflictError:
        await message.answer(
            "⚠️ Для этого чата требуется явная привязка существующей семьи."
        )
        return

    user = await get_user_by_telegram_id(
        telegram_id
    )

    if user:

        if user.family_id != family.id:
            await state.clear()
            await message.answer(
                "⚠️ Этот пользователь уже связан с другой семьёй. "
                "Поддержка участия в нескольких семьях будет добавлена следующим этапом."
            )
            return

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
    await state.update_data(
        registration_family_id=family.id,
        registration_chat_id=chat_id,
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

    data = await state.get_data()
    family_id = data.get("registration_family_id")
    registration_chat_id = data.get("registration_chat_id")
    try:
        family = await require_family_for_chat(message.chat.id)
    except FamilyContextNotFoundError:
        await state.clear()
        await message.answer("Регистрация была начата в другом чате. Начните заново.")
        return

    if (
        registration_chat_id != message.chat.id
        or family_id is None
        or family.id != family_id
    ):
        await state.clear()
        await message.answer("Регистрация была начата в другом чате. Начните заново.")
        return

    await create_user(
        telegram_id=message.from_user.id,
        name=name,
        family_id=family_id,
    )

    await state.clear()

    await message.answer(
        f"✅ Рад познакомиться, <b>{name}</b>!"
    )

    await message.answer(
        WELCOME_TEXT,
        reply_markup=main_menu,
    )
