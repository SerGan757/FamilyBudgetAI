from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from functools import lru_cache
from app.i18n import t


@lru_cache(maxsize=5)
def main_menu_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text=t(language, "menu.history")),
            KeyboardButton(text=t(language, "menu.today")),
        ],
        [
            KeyboardButton(text=t(language, "menu.month")),
            KeyboardButton(text=t(language, "menu.balance")),
        ],
        [
            KeyboardButton(text=t(language, "menu.analytics")),
            KeyboardButton(text=t(language, "menu.delete")),
        ],
        [
            KeyboardButton(text=t(language, "menu.recurring")),
            KeyboardButton(text=t(language, "menu.settings")),
        ],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
    is_persistent=True,
    input_field_placeholder=t(language, "menu.placeholder"),
    )


@lru_cache(maxsize=5)
def back_to_main_menu(language: str = "ru") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=t(language, "menu.back"))]],
    resize_keyboard=True,
    one_time_keyboard=False,
    is_persistent=True,
    )


main_menu = main_menu_keyboard()
back_to_main_menu_keyboard = back_to_main_menu()
