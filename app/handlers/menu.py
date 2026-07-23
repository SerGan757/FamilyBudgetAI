from aiogram import F, Router
from aiogram.types import Message

from app.handlers.delete import delete
from app.handlers.history import history
from app.handlers.statistics import (
    analytics,
    balance,
    month,
    today,
)
from app.handlers.recurring import recurring_menu
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

    await message.answer(
        "Действие отменено.",
        reply_markup=main_menu,
    )


@router.message(F.text == "🗑️ Удалить")
async def delete_menu(message: Message):
    await delete(message)


@router.message(F.text == "📊 Аналитика")
async def analytics_menu(message: Message):

    await analytics(message)


@router.message(F.text == "🔁 Регулярные")
async def recurring(message: Message):

    print(repr(message.text))

    await recurring_menu(message)


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