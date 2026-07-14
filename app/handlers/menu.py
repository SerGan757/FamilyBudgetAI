from aiogram import F, Router
from aiogram.types import Message

from app.handlers.delete import (
    undo,
    waiting_for_delete_id,
)
from app.handlers.history import history
from app.handlers.statistics import (
    balance,
    month,
    today,
)
from app.keyboards.main_menu import main_menu

router = Router()


@router.message(F.text == "➕ Добавить")
async def add(message: Message):

    await message.answer(
        "<b>Добавление операции</b>\n\n"
        "Введите сообщение.\n\n"
        "<pre>"
        "Кофе 3.50\n"
        "Lidl 42.80\n"
        "Бензин 60\n\n"
        "или\n\n"
        "2300 Зарплата"
        "</pre>",
        reply_markup=main_menu,
    )


@router.message(F.text == "📅 Сегодня")
async def today_menu(message: Message):
    await today(message)


@router.message(F.text == "📆 Месяц")
async def month_menu(message: Message):
    await month(message)


@router.message(F.text == "💰 Баланс")
async def balance_menu(message: Message):
    await balance(message)


@router.message(F.text == "📋 История")
async def history_menu(message: Message):
    await history(message)


@router.message(F.text == "↩️ Отменить")
async def undo_menu(message: Message):
    await undo(message)


@router.message(F.text == "🗑️ Удалить")
async def delete_menu(message: Message):

    waiting_for_delete_id.add(message.from_user.id)

    await message.answer(
        "<b>Удаление операции</b>\n\n"
        "Введите только ID.\n\n"
        "Например:\n\n"
        "<pre>125</pre>",
        reply_markup=main_menu,
    )


@router.message(F.text == "📊 Аналитика")
async def analytics(message: Message):

    await message.answer(
        "🚧 Аналитика появится в версии 0.5.",
        reply_markup=main_menu,
    )


@router.message(F.text == "👨‍👩‍👧 Семья")
async def family(message: Message):

    await message.answer(
        "🚧 Семейный бюджет появится в версии 0.6.",
        reply_markup=main_menu,
    )


@router.message(F.text == "⚙️ Еще")
async def more(message: Message):

    await message.answer(
        "<b>Family Budget AI</b>\n\n"
        "<b>Версия:</b> 0.4.3\n"
        "<b>База данных:</b> PostgreSQL\n"
        "<b>AI Parser:</b> В разработке\n\n"
        "Спасибо, что тестируете проект ❤️",
        reply_markup=main_menu,
    )