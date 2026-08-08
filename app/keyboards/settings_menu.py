from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup,
)
from app.services.country_catalog import COUNTRIES
from app.keyboards.projects import button as project_button


class FamilySettingsCallback(CallbackData, prefix="fset"):
    action: str
    value: str = ""


def _inline(text: str, action: str, value: str = "") -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=FamilySettingsCallback(action=action, value=value).pack(),
    )


def temporary_screen_ttl_label(ttl: int) -> str:
    value = "выключено" if ttl == 0 else f"{ttl} сек."
    return f"🧹 Автоудаление экранов: {value}"


def family_settings_keyboard_for_ttl(ttl: int = 20) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_inline("🌐 Язык", "language")],
        [_inline("🌍 Страна", "country")],
        [_inline("🏙 Город", "city")],
        [_inline("🕓 Часовой пояс", "timezone")],
        [_inline("💶 Валюта", "currency")],
        [_inline(temporary_screen_ttl_label(ttl), "temporary_ttl")],
        [project_button("🏷 Проекты", "list")],
        [_inline("ℹ️ О боте", "about")],
        [_inline("⬅️ Назад", "close")],
    ])


family_settings_keyboard = family_settings_keyboard_for_ttl()


def temporary_screen_ttl_keyboard(current_ttl: int) -> InlineKeyboardMarkup:
    rows = []
    for ttl in (5, 10, 20, 30, 60, 0):
        label = "Выключено" if ttl == 0 else f"{ttl} сек."
        marker = "●" if ttl == current_ttl else "○"
        rows.append([_inline(f"{marker} {label}", "set_temporary_ttl", str(ttl))])
    rows.append([_inline("⬅️ Назад", "home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


language_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_inline("🇷🇺 Русский", "set_language", "ru")],
    [_inline("🇺🇦 Українська", "set_language", "uk")],
    [_inline("🇩🇪 Deutsch", "set_language", "de")],
    [_inline("🇬🇧 English", "set_language", "en")],
    [_inline("🇧🇾 Беларуская", "set_language", "be")],
    [_inline("⬅️ Назад", "home")],
])


TIMEZONE_OPTIONS = (
    ("🇩🇪 Berlin", "Europe/Berlin"), ("🇺🇦 Kyiv", "Europe/Kyiv"),
    ("🇵🇱 Warsaw", "Europe/Warsaw"), ("🇨🇿 Prague", "Europe/Prague"),
    ("🇦🇹 Vienna", "Europe/Vienna"), ("🇮🇹 Rome", "Europe/Rome"),
    ("🇪🇸 Madrid", "Europe/Madrid"), ("🇫🇷 Paris", "Europe/Paris"),
    ("🇳🇱 Amsterdam", "Europe/Amsterdam"), ("🇧🇪 Brussels", "Europe/Brussels"),
    ("🇸🇰 Bratislava", "Europe/Bratislava"), ("🇵🇹 Lisbon", "Europe/Lisbon"),
    ("🇷🇴 Bucharest", "Europe/Bucharest"), ("🇧🇬 Sofia", "Europe/Sofia"),
    ("🇬🇧 London", "Europe/London"), ("🇨🇭 Zurich", "Europe/Zurich"),
    ("🇭🇺 Budapest", "Europe/Budapest"), ("🇸🇪 Stockholm", "Europe/Stockholm"),
    ("🇳🇴 Oslo", "Europe/Oslo"), ("🇩🇰 Copenhagen", "Europe/Copenhagen"),
    ("🌐 UTC", "UTC"),
)
timezone_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    *[[_inline(label, "set_timezone", value)] for label, value in TIMEZONE_OPTIONS],
    [_inline("⬅️ Назад", "home")],
])


CURRENCY_OPTIONS = (
    ("EUR (€)", "EUR"), ("USD ($)", "USD"), ("UAH (₴)", "UAH"),
    ("GBP (£)", "GBP"), ("PLN (zł)", "PLN"), ("CZK (Kč)", "CZK"),
    ("RON (lei)", "RON"), ("CHF (CHF)", "CHF"), ("HUF (Ft)", "HUF"),
    ("SEK (kr)", "SEK"), ("NOK (kr)", "NOK"), ("DKK (kr)", "DKK"),
)
currency_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    *[[_inline(label, "set_currency", value)] for label, value in CURRENCY_OPTIONS],
    [_inline("⬅️ Назад", "home")],
])


settings_cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_inline("❌ Отмена", "cancel")],
])

settings_about_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_inline("⬅️ Назад", "home")],
])


COUNTRIES_PER_PAGE = 10


def country_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    last_page = max(0, (len(COUNTRIES) - 1) // COUNTRIES_PER_PAGE)
    page = min(max(page, 0), last_page)
    start = page * COUNTRIES_PER_PAGE
    rows = [
        [_inline(f"{country.flag} {country.name}", "set_country", country.code)]
        for country in COUNTRIES[start:start + COUNTRIES_PER_PAGE]
    ]
    navigation = []
    if page > 0:
        navigation.append(_inline("⬅️", "country_page", str(page - 1)))
    if page < last_page:
        navigation.append(_inline("➡️", "country_page", str(page + 1)))
    if navigation:
        rows.append(navigation)
    rows.append([_inline("⬅️ Назад", "home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


settings_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👨‍👩‍👧 Семья"), KeyboardButton(text="👥 Участники")],
        [KeyboardButton(text="🏷 Категории"), KeyboardButton(text="💶 Валюта")],
        [KeyboardButton(text="📤 Экспорт"), KeyboardButton(text="💾 Резервная копия")],
        [KeyboardButton(text="ℹ️ О боте"), KeyboardButton(text="⬅️ Главное меню")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
    is_persistent=True,
)
