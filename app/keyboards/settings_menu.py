from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup,
)
from app.services.country_catalog import COUNTRIES
from app.keyboards.projects import button as project_button
from app.utils.currency import CURRENCY_SYMBOLS
from app.i18n import country_name, t, timezone_name
from app.keyboards.savings_goal import GoalCallback
from app.keyboards.categories import CategoryCallback


class FamilySettingsCallback(CallbackData, prefix="fset"):
    action: str
    value: str = ""


def _inline(text: str, action: str, value: str = "") -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=FamilySettingsCallback(action=action, value=value).pack(),
    )


def temporary_screen_ttl_label(ttl: int, language: str = "ru") -> str:
    value = t(language, "settings.off") if ttl == 0 else t(language, "settings.seconds", value=ttl)
    return t(language, "settings.ttl", value=value)


def family_settings_keyboard_for_ttl(ttl: int = 20, language: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_inline(t(language, "menu.documents"), "documents")],
        [InlineKeyboardButton(
            text=t(language, "settings.categories"),
            callback_data=CategoryCallback(action="list", value="settings").pack(),
        )],
        [project_button(t(language, "settings.projects"), "list")],
        [InlineKeyboardButton(
            text=t(language, "settings.savings_goal"),
            callback_data=GoalCallback(action="show").pack(),
        )],
        [_inline(t(language, "settings.language"), "language")],
        [_inline(t(language, "settings.country"), "country")],
        [_inline(t(language, "settings.city"), "city")],
        [_inline(t(language, "settings.timezone"), "timezone")],
        [_inline(t(language, "settings.currency"), "currency")],
        [_inline(temporary_screen_ttl_label(ttl, language), "temporary_ttl")],
        [_inline(t(language, "settings.about"), "about")],
        [_inline(t(language, "nav.back"), "close")],
    ])


family_settings_keyboard = family_settings_keyboard_for_ttl()


def temporary_screen_ttl_keyboard(current_ttl: int, language: str = "ru") -> InlineKeyboardMarkup:
    rows = []
    for ttl in (5, 10, 20, 30, 60, 0):
        label = t(language, "settings.off") if ttl == 0 else t(language, "settings.seconds", value=ttl)
        marker = "●" if ttl == current_ttl else "○"
        rows.append([_inline(f"{marker} {label}", "set_temporary_ttl", str(ttl))])
    rows.append([_inline(t(language, "nav.back"), "home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


LANGUAGE_OPTIONS = (
    ("🇷🇺 Русский", "ru"), ("🇺🇦 Українська", "uk"),
    ("🇩🇪 Deutsch", "de"), ("🇬🇧 English", "en"),
    ("🇧🇾 Беларуская", "be"), ("🇵🇱 Polski", "pl"),
    ("🇨🇿 Čeština", "cs"), ("🇸🇰 Slovenčina", "sk"),
    ("🇷🇴 Română", "ro"), ("🇧🇬 Български", "bg"),
    ("🇭🇺 Magyar", "hu"),
)

def language_keyboard_for(current_language: str = "ru") -> InlineKeyboardMarkup:
    rows = [
        [_inline(f"{'✅ ' if code == current_language else ''}{label}", "set_language", code)]
        for label, code in LANGUAGE_OPTIONS
    ]
    rows.append([_inline(t(current_language, "nav.back"), "home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

language_keyboard = language_keyboard_for("")


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
def timezone_keyboard_for(language: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        *[[_inline(f"{label.split()[0]} {timezone_name(language, value)}", "set_timezone", value)] for label, value in TIMEZONE_OPTIONS],
        [_inline(t(language, "nav.back"), "home")],
    ])


timezone_keyboard = timezone_keyboard_for()


CURRENCY_OPTIONS = tuple(
    (f"{code} ({symbol})", code) for code, symbol in CURRENCY_SYMBOLS.items()
)
def currency_keyboard_for(language: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        *[[_inline(label, "set_currency", value)] for label, value in CURRENCY_OPTIONS],
        [_inline(t(language, "nav.back"), "home")],
    ])


currency_keyboard = currency_keyboard_for()


def settings_cancel_keyboard_for(language: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_inline(t(language, "goal.cancel"), "cancel")],
    ])


settings_cancel_keyboard = settings_cancel_keyboard_for()

def settings_about_keyboard_for(language: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_inline(t(language, "nav.back"), "home")]])

settings_about_keyboard = settings_about_keyboard_for()


COUNTRIES_PER_PAGE = 10


def country_keyboard(page: int = 0, language: str = "ru") -> InlineKeyboardMarkup:
    last_page = max(0, (len(COUNTRIES) - 1) // COUNTRIES_PER_PAGE)
    page = min(max(page, 0), last_page)
    start = page * COUNTRIES_PER_PAGE
    rows = [
        [_inline(f"{country.flag} {country_name(language, country.code)}", "set_country", country.code)]
        for country in COUNTRIES[start:start + COUNTRIES_PER_PAGE]
    ]
    navigation = []
    if page > 0:
        navigation.append(_inline("⬅️", "country_page", str(page - 1)))
    if page < last_page:
        navigation.append(_inline("➡️", "country_page", str(page + 1)))
    if navigation:
        rows.append(navigation)
    rows.append([_inline(t(language, "nav.back"), "home")])
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
