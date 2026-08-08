from html import escape

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.constants import APP_NAME, APP_VERSION, DEVELOPER_NAME, DEVELOPER_TELEGRAM
from app.keyboards.main_menu import back_to_main_menu_keyboard
from app.handlers.settings_states import FamilySettingsState
from app.keyboards.settings_menu import (
    FamilySettingsCallback, currency_keyboard, family_settings_keyboard_for_ttl,
    country_keyboard, language_keyboard, settings_about_keyboard,
    settings_cancel_keyboard, settings_menu,
    temporary_screen_ttl_keyboard, timezone_keyboard,
)
from app.services.country_catalog import get_country
from app.services.settings_service import (
    CURRENCY_CODES, LANGUAGE_CODES, TIMEZONE_VALUES, get_current_family_settings,
    TEMPORARY_SCREEN_TTL_VALUES, get_family_members, get_family_settings_data,
    update_current_family_setting, update_family_temporary_screen_ttl,
    update_current_family_country, validate_family_setting,
)
from app.services.family_context_service import require_family_for_chat


router = Router()


async def _get_data_or_show_error(message: Message):
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type,
        telegram_id=message.from_user.id,
    )
    data = await get_family_settings_data(family.id)
    if data is None:
        await message.answer(
            "⚠️ Не удалось найти пользователя или его семью.",
            reply_markup=back_to_main_menu_keyboard,
        )
    return data


def _created_line(created_at) -> str:
    return "" if created_at is None else f"\n📅 <b>Создана:</b> {created_at:%d.%m.%Y}"


LANGUAGE_LABELS = {
    "ru": "Русский", "uk": "Українська", "de": "Deutsch", "en": "English",
    "be": "Беларуская",
}
CURRENCY_SYMBOLS = {
    "EUR": "€", "USD": "$", "UAH": "₴", "GBP": "£", "PLN": "zł", "CZK": "Kč",
    "RON": "lei", "CHF": "CHF", "HUF": "Ft", "SEK": "kr", "NOK": "kr", "DKK": "kr",
}


def family_settings_text(data: dict, notice: str | None = None) -> str:
    language = LANGUAGE_LABELS.get(data["language"], data["language"])
    currency = data["currency"]
    country = get_country(data["country"])
    country_label = f"{country.flag} {country.name}" if country else (data["country"] or "—")
    prefix = f"{notice}\n\n" if notice else ""
    return (
        f"{prefix}⚙️ <b>Настройки семьи</b>\n\n"
        f"🌐 Язык: {escape(language)}\n"
        f"🌍 Страна: {escape(country_label)}\n"
        f"🏙 Город: {escape(data['city'] or '—')}\n"
        f"🕓 Часовой пояс: {escape(data['timezone'])}\n"
        f"💶 Валюта: {escape(currency)} ({CURRENCY_SYMBOLS.get(currency, '')})"
    )


def about_text() -> str:
    return (
        "ℹ️ <b>О боте</b>\n\n"
        f"🤖 <b>{escape(APP_NAME)}</b>\n\n"
        "Семейный Telegram-бот для простого совместного\n"
        "учёта домашних финансов.\n\n"
        "👨‍👩‍👧‍👦 Создайте группу в Telegram, добавьте семью\n"
        "и этого бота — и ведите семейный бюджет вместе.\n\n"
        "💰 <b>Возможности:</b>\n"
        "• быстрый ввод доходов и расходов;\n"
        "• совместный бюджет семьи;\n"
        "• история операций;\n"
        "• баланс и месячная аналитика;\n"
        "• регулярные платежи;\n"
        "• статистика по категориям;\n"
        "• семейные проекты — отпуск, ремонт, дача и другие;\n"
        "• привязка расходов к проекту через #тег;\n"
        "• настройки страны, валюты, языка и часового пояса.\n\n"
        "⚡ <b>Простой ввод:</b>\n"
        "<code>кофе 5\n+2000 зарплата\nкраска 40 #ремонт</code>\n\n"
        f"👨‍💻 Разработчик: {escape(DEVELOPER_NAME)}\n"
        f"✈️ Telegram: {escape(DEVELOPER_TELEGRAM)}\n\n"
        f"🏷 Версия: {escape(APP_VERSION)}"
    )


async def _current_settings_or_error(message: Message, telegram_id: int):
    data = await get_current_family_settings(telegram_id)
    if data is None:
        await message.answer(
            "⚠️ Не удалось найти пользователя или его семью.",
            reply_markup=back_to_main_menu_keyboard,
        )
    return data


@router.message(StateFilter(None), F.text == "⚙️ Настройки")
async def open_settings(message: Message):
    data = await _current_settings_or_error(message, message.from_user.id)
    if data is None:
        return
    await message.answer(
        family_settings_text(data),
        reply_markup=family_settings_keyboard_for_ttl(data["temporary_screen_ttl"]),
        parse_mode="HTML",
    )


async def _show_current_settings(message: Message, telegram_id: int, notice: str | None = None):
    data = await _current_settings_or_error(message, telegram_id)
    if data is not None:
        await message.edit_text(
            family_settings_text(data, notice),
            reply_markup=family_settings_keyboard_for_ttl(data["temporary_screen_ttl"]),
            parse_mode="HTML",
        )
    return data


@router.callback_query(FamilySettingsCallback.filter())
async def family_settings_callback(
    callback: CallbackQuery, callback_data: FamilySettingsCallback, state: FSMContext,
):
    message = callback.message
    if message is None:
        await callback.answer()
        return
    action, value = callback_data.action, callback_data.value
    current = await get_current_family_settings(callback.from_user.id)
    if current is None:
        await state.clear()
        await callback.answer("Пользователь или семья не найдены.", show_alert=True)
        return
    if action in {"home", "cancel"}:
        await state.clear()
        await _show_current_settings(message, callback.from_user.id)
    elif action == "close":
        await state.clear()
        await message.delete()
    elif action == "language":
        await message.edit_text("🌐 Выберите язык семьи:", reply_markup=language_keyboard)
    elif action == "timezone":
        await message.edit_text("🕓 Выберите часовой пояс:", reply_markup=timezone_keyboard)
    elif action == "currency":
        await message.edit_text("💶 Выберите валюту:", reply_markup=currency_keyboard)
    elif action == "temporary_ttl":
        await message.edit_text(
            "🧹 <b>Автоудаление экранов</b>\n\n"
            "Через сколько удалять информационные экраны?",
            reply_markup=temporary_screen_ttl_keyboard(current["temporary_screen_ttl"]),
            parse_mode="HTML",
        )
    elif action == "country":
        await message.edit_text("🌍 Выберите страну:", reply_markup=country_keyboard())
    elif action == "about":
        await message.edit_text(
            about_text(), reply_markup=settings_about_keyboard, parse_mode="HTML",
        )
    elif action == "country_page":
        try:
            page = int(value)
        except ValueError:
            await callback.answer("Недопустимая страница.", show_alert=True)
            return
        await message.edit_text("🌍 Выберите страну:", reply_markup=country_keyboard(page))
    elif action == "city":
        await state.set_state(FamilySettingsState.waiting_for_city)
        await message.edit_text(
            "Введите город (до 100 символов):", reply_markup=settings_cancel_keyboard,
        )
    elif action == "set_country":
        try:
            updated = await update_current_family_country(callback.from_user.id, value)
        except ValueError:
            await callback.answer("Недопустимая страна.", show_alert=True)
            return
        if not updated:
            await callback.answer("Пользователь или семья не найдены.", show_alert=True)
            return
        await _show_current_settings(
            message, callback.from_user.id,
            "✅ Страна сохранена.\nВалюта и часовой пояс установлены автоматически.",
        )
    elif action == "set_temporary_ttl":
        try:
            ttl = int(value)
        except ValueError:
            ttl = -1
        if ttl not in TEMPORARY_SCREEN_TTL_VALUES:
            await callback.answer("Недопустимое значение.", show_alert=True)
            return
        family = await require_family_for_chat(
            message.chat.id, chat_type=message.chat.type,
            telegram_id=callback.from_user.id,
        )
        updated = await update_family_temporary_screen_ttl(family.id, ttl)
        if not updated:
            await callback.answer("Пользователь или семья не найдены.", show_alert=True)
            return
        notice = "✅ Автоудаление выключено." if ttl == 0 else f"✅ Автоудаление: {ttl} сек."
        await _show_current_settings(message, callback.from_user.id, notice)
    elif action.startswith("set_"):
        field = action.removeprefix("set_")
        allowed = {"language": LANGUAGE_CODES, "timezone": TIMEZONE_VALUES, "currency": CURRENCY_CODES}
        if field not in allowed or value not in allowed[field]:
            await callback.answer("Недопустимое значение.", show_alert=True)
            return
        updated = await update_current_family_setting(callback.from_user.id, field, value)
        if not updated:
            await callback.answer("Пользователь или семья не найдены.", show_alert=True)
            return
        notices = {"language": "✅ Язык сохранён.", "timezone": "✅ Часовой пояс сохранён.", "currency": "✅ Валюта сохранена."}
        await _show_current_settings(message, callback.from_user.id, notices[field])
    else:
        await callback.answer("Неизвестное действие.", show_alert=True)
        return
    await callback.answer()


async def _save_location(message: Message, state: FSMContext, field: str) -> None:
    try:
        value = validate_family_setting(field, message.text or "")
    except ValueError:
        await message.answer(
            "Введите непустое значение до 100 символов. Команды использовать нельзя.",
            reply_markup=settings_cancel_keyboard,
        )
        return
    updated = await update_current_family_setting(message.from_user.id, field, value)
    if not updated:
        await state.clear()
        await message.answer(
            "⚠️ Не удалось найти пользователя или его семью.",
            reply_markup=back_to_main_menu_keyboard,
        )
        return
    await state.clear()
    data = await get_current_family_settings(message.from_user.id)
    notice = "✅ Страна сохранена." if field == "country" else "✅ Город сохранён."
    await message.answer(
        family_settings_text(data, notice),
        reply_markup=family_settings_keyboard_for_ttl(data["temporary_screen_ttl"]),
        parse_mode="HTML",
    )


@router.message(FamilySettingsState.waiting_for_city)
async def save_city(message: Message, state: FSMContext):
    await _save_location(message, state, "city")


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
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type,
        telegram_id=message.from_user.id,
    )
    family_members = await get_family_members(family.id)
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


@router.message(StateFilter(None), F.text.in_({"ℹ️ О боте", "ℹ️ О программе"}))
async def about(message: Message):
    await message.answer(
        about_text(), reply_markup=settings_menu, parse_mode="HTML",
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
