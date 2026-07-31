from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


settings_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👨‍👩‍👧 Семья"), KeyboardButton(text="👥 Участники")],
        [KeyboardButton(text="🏷 Категории"), KeyboardButton(text="💶 Валюта")],
        [KeyboardButton(text="📤 Экспорт"), KeyboardButton(text="💾 Резервная копия")],
        [KeyboardButton(text="ℹ️ О программе"), KeyboardButton(text="⬅️ Главное меню")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
    is_persistent=True,
)
