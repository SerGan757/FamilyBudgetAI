from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="📋 История"),
            KeyboardButton(text="📅 Сегодня"),
        ],
        [
            KeyboardButton(text="📅 Месяц"),
            KeyboardButton(text="💰 Баланс"),
        ],
        [
            KeyboardButton(text="📊 Аналитика"),
            KeyboardButton(text="🗑️ Удалить"),
        ],
        [
            KeyboardButton(text="🔁 Регулярные"),
            KeyboardButton(text="⚙️ Настройки"),
        ],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
    is_persistent=True,
    input_field_placeholder="Введите расход или выберите действие...",
)


back_to_main_menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="⬅️ Главное меню")]],
    resize_keyboard=True,
    one_time_keyboard=False,
    is_persistent=True,
)
