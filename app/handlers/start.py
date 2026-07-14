from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.keyboards.main_menu import main_menu

router = Router()


WELCOME_TEXT = """
👋 <b>Добро пожаловать в Family Budget AI</b>

Ваш персональный помощник по учету финансов.

<b>Как добавить расход</b>

<pre>
Кофе 3.50
Lidl 42.80
Shell 65
</pre>

<b>Как добавить доход</b>

<pre>
2300 Зарплата
150 Возврат долга
</pre>

════════════════════

<b>Возможности</b>

🛒 Расходы

💰 Доходы

📊 Статистика

📖 История

🤖 Автоматические категории

════════════════════

Выберите действие кнопками ниже.
"""


@router.message(Command("start"))
async def cmd_start(message: Message):

    await message.answer(
        WELCOME_TEXT,
        reply_markup=main_menu,
    )