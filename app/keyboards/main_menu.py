from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="➕ Добавить"),
            KeyboardButton(text="📋 История"),
        ],
        [
            KeyboardButton(text="📅 Сегодня"),
            KeyboardButton(text="📆 Месяц"),
        ],
        [
            KeyboardButton(text="💰 Баланс"),
            KeyboardButton(text="↩️ Отменить"),
        ],
        [
            KeyboardButton(text="🗑️ Удалить"),
            KeyboardButton(text="📊 Аналитика"),
        ],
        [
            KeyboardButton(text="👨‍👩‍👧 Семья"),
            KeyboardButton(text="⚙️ Еще"),
        ],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
    is_persistent=True,
    input_field_placeholder="Введите расход или выберите действие...",
)