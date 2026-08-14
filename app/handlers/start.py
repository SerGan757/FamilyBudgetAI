from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.handlers.user_states import RegistrationState
from app.keyboards.main_menu import main_menu_keyboard
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
from app.i18n import family_language, normalize_telegram_language, t
from app.utils.currency import currency_symbol, family_currency

router = Router()


def welcome_text(family, returning_name: str | None = None) -> str:
    """Build the actual /start welcome from the shared onboarding content."""
    language = family_language(family)
    onboarding = t(
        language, "onboarding.about",
        currency=currency_symbol(family_currency(family)),
    )
    # About and /start share one body; /start supplies its context-aware greeting.
    _, body = onboarding.split("\n", 1)
    greeting = (
        t(language, "start.returning", name=escape(returning_name))
        if returning_name is not None
        else t(language, "start.welcome")
    )
    return f"{greeting}\n{body}"


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
            welcome_text(family, user.name),
            reply_markup=main_menu_keyboard(family_language(family)),
            parse_mode="HTML",
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
        f"{welcome_text(family)}\n\n{t(family_language(family), 'start.ask_name')}",
        parse_mode="HTML",
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
        t(family_language(family), "start.registered", name=escape(name)),
        reply_markup=main_menu_keyboard(family_language(family)),
        parse_mode="HTML",
    )
