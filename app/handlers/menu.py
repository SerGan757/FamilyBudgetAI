from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter
from aiogram.types import Message

from app.handlers.delete import delete
from app.handlers.history import history
from app.handlers.statistics import (
    analytics,
    balance,
    month,
    today,
)
from app.handlers.recurring import recurring_menu
from app.keyboards.main_menu import back_to_main_menu_keyboard, main_menu
from app.keyboards.main_menu import main_menu_keyboard
from app.i18n import all_texts, family_language, t
from app.services.family_context_service import FamilyContextNotFoundError, require_family_for_chat

router = Router()


@router.message(Command("menu"))
async def show_menu(message: Message):
    try:
        family = await require_family_for_chat(
            message.chat.id, chat_type=message.chat.type,
            telegram_id=message.from_user.id,
        )
        language = family_language(family)
    except FamilyContextNotFoundError:
        language = "ru"
    await message.answer(t(language, "menu.title"), reply_markup=main_menu_keyboard(language))


@router.message(F.text == "➕ Добавить")
async def add(message: Message):

    await message.answer(
        "<b>Добавление операции</b>\n\n"
        "Введите сообщение.\n\n"
        "<pre>"
        "Кофе 3.50\n"
        "Lidl 42.80\n"
        "Бензин 60\n\n"
        "или\n\n"
        "2300 Зарплата"
        "</pre>",
        reply_markup=back_to_main_menu_keyboard,
    )


@router.message(F.text.in_(all_texts("menu.today")))
async def today_menu(message: Message):
    await today(message)


@router.message(StateFilter(None), F.text.in_(all_texts("menu.month")))
async def month_menu(message: Message):
    await month(message)
    return


@router.message(F.text.in_(all_texts("menu.balance")))
async def balance_menu(message: Message):
    await balance(message)


@router.message(F.text.in_(all_texts("menu.history")))
async def history_menu(message: Message):
    await history(message)


@router.message(F.text.in_(all_texts("menu.delete")))
async def delete_menu(message: Message, state: FSMContext):
    await delete(message, state)


@router.message(F.text.in_(all_texts("menu.analytics")))
async def analytics_menu(message: Message):

    await analytics(message)


@router.message(F.text.in_(all_texts("menu.recurring")))
async def recurring(message: Message):

    print(repr(message.text))

    await recurring_menu(message)
