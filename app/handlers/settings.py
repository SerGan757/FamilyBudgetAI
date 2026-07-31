from html import escape

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import Message

from app.constants import APP_VERSION
from app.keyboards.main_menu import back_to_main_menu_keyboard
from app.keyboards.settings_menu import settings_menu
from app.services.settings_service import get_family_members, get_family_settings_data


router = Router()


async def _get_data_or_show_error(message: Message):
    data = await get_family_settings_data(message.from_user.id)
    if data is None:
        await message.answer(
            "⚠️ Не удалось найти пользователя или его семью.",
            reply_markup=back_to_main_menu_keyboard,
        )
    return data


def _created_line(created_at) -> str:
    return "" if created_at is None else f"\n📅 <b>Создана:</b> {created_at:%d.%m.%Y}"


@router.message(StateFilter(None), F.text == "⚙️ Настройки")
async def open_settings(message: Message):
    data = await _get_data_or_show_error(message)
    if data is None:
        return

    text = (
        "⚙️ <b>Настройки</b>\n\n"
        f"👨‍👩‍👧 <b>Семья:</b> {escape(data['name'])}\n"
        f"👥 <b>Участников:</b> {data['members_count']}\n"
        f"📋 <b>Операций:</b> {data['transactions_count']}"
        f"{_created_line(data['created_at'])}\n\nВыберите раздел."
    )
    await message.answer(text, reply_markup=settings_menu, parse_mode="HTML")


@router.message(StateFilter(None), F.text == "👨‍👩‍👧 Семья")
async def family_info(message: Message):
    data = await _get_data_or_show_error(message)
    if data is None:
        return

    text = (
        "👨‍👩‍👧 <b>Семья</b>\n\n"
        f"Название: {escape(data['name'])}\n"
        f"ID семьи: {data['id']}\n"
        f"Участников: {data['members_count']}\n"
        f"Операций: {data['transactions_count']}\n"
        f"Регулярных шаблонов: {data['recurring_count']}"
    )
    await message.answer(text, reply_markup=settings_menu, parse_mode="HTML")


@router.message(StateFilter(None), F.text == "👥 Участники")
async def members(message: Message):
    family_members = await get_family_members(message.from_user.id)
    if family_members is None:
        await message.answer(
            "⚠️ Не удалось найти пользователя или его семью.",
            reply_markup=back_to_main_menu_keyboard,
        )
        return

    text = "👥 <b>Участники семьи</b>\n\n"
    for index, member in enumerate(family_members, start=1):
        text += f"{index}. {escape(member.name)}\n"
    text += f"\nВсего: {len(family_members)}"
    await message.answer(text, reply_markup=settings_menu, parse_mode="HTML")


@router.message(StateFilter(None), F.text == "ℹ️ О программе")
async def about(message: Message):
    await message.answer(
        "ℹ️ <b>О программе</b>\n\n"
        "FamilyBudgetAI\n"
        f"Версия: {APP_VERSION}\n"
        "База данных: PostgreSQL\n"
        "Статус: активная разработка\n\n"
        "Основные функции:\n"
        "• расходы и доходы;\n• история;\n• баланс;\n• аналитика;\n"
        "• регулярные платежи;\n• семейный доступ.",
        reply_markup=settings_menu,
        parse_mode="HTML",
    )


@router.message(
    StateFilter(None),
    F.text.in_({"🏷 Категории", "💶 Валюта", "📤 Экспорт", "💾 Резервная копия"}),
)
async def coming_soon(message: Message):
    await message.answer(
        f"{escape(message.text)}\n\nРаздел находится в разработке.",
        reply_markup=settings_menu,
        parse_mode="HTML",
    )
