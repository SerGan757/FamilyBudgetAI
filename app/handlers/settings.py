from html import escape

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.constants import APP_VERSION, DEVELOPER_NAME, DEVELOPER_TELEGRAM
from app.keyboards.main_menu import back_to_main_menu_keyboard, main_menu_keyboard
from app.handlers.settings_states import FamilySettingsState
from app.keyboards.settings_menu import (
    FamilySettingsCallback, currency_keyboard_for, family_settings_keyboard_for_ttl,
    country_keyboard, language_keyboard, language_keyboard_for, settings_about_keyboard_for,
    settings_cancel_keyboard_for, settings_menu,
    temporary_screen_ttl_keyboard, timezone_keyboard_for,
)
from app.services.country_catalog import get_country
from app.services.settings_service import (
    CURRENCY_CODES, LANGUAGE_CODES, TIMEZONE_VALUES, get_current_family_settings,
    TEMPORARY_SCREEN_TTL_VALUES, get_family_members, get_family_settings_data,
    update_current_family_setting, update_family_temporary_screen_ttl,
    update_current_family_country, validate_family_setting,
)
from app.services.family_context_service import require_family_for_chat
from app.utils.currency import currency_symbol, normalize_currency_code
from app.i18n import all_texts, country_name, normalize_language, t, timezone_name


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
    "be": "Беларуская", "pl": "Polski", "cs": "Čeština", "sk": "Slovenčina",
    "ro": "Română", "bg": "Български", "hu": "Magyar",
}
def family_settings_text(data: dict, notice: str | None = None) -> str:
    language_code = normalize_language(data.get("language"))
    language = LANGUAGE_LABELS.get(language_code, language_code)
    currency = normalize_currency_code(data["currency"])
    country = get_country(data["country"])
    country_label = f"{country.flag} {country_name(language_code, country.code)}" if country else (data["country"] or "—")
    prefix = f"{notice}\n\n" if notice else ""
    return (
        f"{prefix}⚙️ <b>{t(language_code, 'settings.title')}</b>\n\n"
        f"{t(language_code, 'settings.language')}: {escape(language)}\n"
        f"{t(language_code, 'settings.country')}: {escape(country_label)}\n"
        f"{t(language_code, 'settings.city')}: {escape(data['city'] or '—')}\n"
        f"{t(language_code, 'settings.timezone')}: {escape(timezone_name(language_code, data['timezone']))}\n"
        f"{t(language_code, 'settings.currency')}: {escape(currency)} ({currency_symbol(currency)})"
    )


def about_text(language: str = "ru", currency_code: str = "EUR") -> str:
    currency = currency_symbol(normalize_currency_code(currency_code))
    return (
        f"ℹ️ <b>{t(language, 'about.title')}</b>\n\n"
        f"{t(language, 'onboarding.about', currency=currency)}\n\n"
        f"👨‍💻 {t(language, 'about.developer')}: {escape(DEVELOPER_NAME)}\n"
        f"✈️ Telegram: {escape(DEVELOPER_TELEGRAM)}\n"
        f"🏷 {t(language, 'about.version')}: {escape(APP_VERSION)}"
    )


async def _current_settings_or_error(message: Message, telegram_id: int):
    data = await get_current_family_settings(telegram_id)
    if data is None:
        await message.answer(
            "⚠️ Не удалось найти пользователя или его семью.",
            reply_markup=back_to_main_menu_keyboard,
        )
    return data


@router.message(StateFilter(None), F.text.in_(all_texts("menu.settings")))
async def open_settings(message: Message):
    data = await _current_settings_or_error(message, message.from_user.id)
    if data is None:
        return
    await message.answer(
        family_settings_text(data),
        reply_markup=family_settings_keyboard_for_ttl(data["temporary_screen_ttl"], data["language"]),
        parse_mode="HTML",
    )


async def _show_current_settings(message: Message, telegram_id: int, notice: str | None = None):
    data = await _current_settings_or_error(message, telegram_id)
    if data is not None:
        await message.edit_text(
            family_settings_text(data, notice),
            reply_markup=family_settings_keyboard_for_ttl(data["temporary_screen_ttl"], data["language"]),
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
        await callback.answer(t("ru", "settings.not_found"), show_alert=True)
        return
    language = normalize_language(current.get("language"))
    if action in {"home", "cancel"}:
        await state.clear()
        await _show_current_settings(message, callback.from_user.id)
    elif action == "close":
        await state.clear()
        await message.delete()
    elif action == "language":
        await message.edit_text(t(language, "settings.select_language"), reply_markup=language_keyboard_for(language))
    elif action == "timezone":
        await message.edit_text(t(language, "settings.select_timezone"), reply_markup=timezone_keyboard_for(language))
    elif action == "currency":
        await message.edit_text(t(language, "settings.select_currency"), reply_markup=currency_keyboard_for(language))
    elif action == "temporary_ttl":
        await message.edit_text(
            f"🧹 <b>{t(language, 'settings.ttl_title').removeprefix('🧹 ')}</b>\n\n"
            f"{t(language, 'settings.ttl_question')}",
            reply_markup=temporary_screen_ttl_keyboard(current["temporary_screen_ttl"], language),
            parse_mode="HTML",
        )
    elif action == "country":
        await message.edit_text(t(language, "settings.select_country"), reply_markup=country_keyboard(language=language))
    elif action == "about":
        await message.edit_text(
            about_text(language, current["currency"]),
            reply_markup=settings_about_keyboard_for(language), parse_mode="HTML",
        )
    elif action == "documents":
        await state.clear()
        from app.handlers.documents import show_documents
        await show_documents(message, callback.from_user.id)
    elif action == "country_page":
        try:
            page = int(value)
        except ValueError:
            await callback.answer("Недопустимая страница.", show_alert=True)
            return
        await message.edit_text(t(language, "settings.select_country"), reply_markup=country_keyboard(page, language))
    elif action == "city":
        await state.set_state(FamilySettingsState.waiting_for_city)
        if hasattr(state, "update_data"):
            await state.update_data(settings_language=language)
        await message.edit_text(
            t(language, "settings.enter_city"), reply_markup=settings_cancel_keyboard_for(language),
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
            t(language, "settings.saved_country"),
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
        ttl_value = t(language, "settings.off") if ttl == 0 else t(language, "settings.seconds", value=ttl)
        notice = t(language, "settings.ttl_saved", value=ttl_value)
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
        updated_language = value if field == "language" else language
        notices = {"language": "settings.saved_language", "timezone": "settings.saved_timezone", "currency": "settings.saved_currency"}
        notice = t(updated_language, notices[field])
        if field == "language":
            await _show_current_settings(message, callback.from_user.id)
            await message.answer(
                notice,
                reply_markup=main_menu_keyboard(updated_language),
            )
        else:
            await _show_current_settings(message, callback.from_user.id, notice)
    else:
        await callback.answer("Неизвестное действие.", show_alert=True)
        return
    await callback.answer()


async def _save_location(message: Message, state: FSMContext, field: str) -> None:
    language = "ru"
    if hasattr(state, "get_data"):
        state_data = await state.get_data()
        language = normalize_language(state_data.get("settings_language"))
    try:
        value = validate_family_setting(field, message.text or "")
    except ValueError:
        await message.answer(
            "Введите непустое значение до 100 символов. Команды использовать нельзя.",
            reply_markup=settings_cancel_keyboard_for(language),
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
    language = normalize_language(data.get("language"))
    notice = t(language, "settings.saved_country") if field == "country" else t(language, "settings.saved_city")
    await message.answer(
        family_settings_text(data, notice),
        reply_markup=family_settings_keyboard_for_ttl(data["temporary_screen_ttl"], data["language"]),
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
    F.text.in_({"💶 Валюта", "📤 Экспорт", "💾 Резервная копия"}),
)
async def coming_soon(message: Message):
    await message.answer(
        f"{escape(message.text)}\n\nРаздел находится в разработке.",
        reply_markup=settings_menu,
        parse_mode="HTML",
    )
