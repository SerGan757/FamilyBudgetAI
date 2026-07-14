from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.services.statistics_service import (
    get_balance,
    get_month_statistics,
    get_today_statistics,
)

router = Router()


def money(value: float) -> str:
    return f"{value:.2f} €"


@router.message(Command("today"))
async def today(message: Message):

    income, expense = await get_today_statistics()

    balance = income - expense

    text = (
        "<pre>"
        "📅 СЕГОДНЯ\n"
        "══════════════════════════════\n\n"
        f"💰 Доходы   : {money(income):>12}\n"
        f"💸 Расходы  : {money(expense):>12}\n"
        "──────────────────────────────\n"
        f"📈 Баланс   : {money(balance):>12}"
        "</pre>"
    )

    await message.answer(text)


@router.message(Command("month"))
async def month(message: Message):

    income, expense = await get_month_statistics()

    balance = income - expense

    month_name = date.today().strftime("%B")

    text = (
        "<pre>"
        f"📆 {month_name.upper()}\n"
        "══════════════════════════════\n\n"
        f"💰 Доходы   : {money(income):>12}\n"
        f"💸 Расходы  : {money(expense):>12}\n"
        "──────────────────────────────\n"
        f"📈 Баланс   : {money(balance):>12}"
        "</pre>"
    )

    await message.answer(text)


@router.message(Command("balance"))
async def balance(message: Message):

    income, expense = await get_balance()

    balance_value = income - expense

    text = (
        "<pre>"
        "💰 ОБЩИЙ БАЛАНС\n"
        "══════════════════════════════\n\n"
        f"💵 Доходы   : {money(income):>12}\n"
        f"💸 Расходы  : {money(expense):>12}\n"
        "──────────────────────────────\n"
        f"💎 Остаток  : {money(balance_value):>12}"
        "</pre>"
    )

    await message.answer(text)