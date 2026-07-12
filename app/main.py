import asyncio
import os

from app.services.expense_service import save_transaction
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv
from app.services.parser import parse_message
from app.services.statistics_service import (
    get_today_transactions,
    get_month_transactions,
    get_month_summary,
)
from app.services.balance_service import get_balance

from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("balance"))
async def balance(message: Message):

    income, expense, balance = await get_balance()

    await message.answer(
        f"""💰 Баланс

📈 Доходы: {income:.2f} €

📉 Расходы: {expense:.2f} €

────────────────

💵 Остаток: {balance:.2f} €"""
    )

@dp.message(Command("today"))
async def today(message: Message):

    transactions = await get_today_transactions()

    if not transactions:
        await message.answer("Сегодня операций нет.")
        return

    text = "📅 Сегодня\n\n"

    total = 0

    for t in transactions:
        text += f"{t.category} {t.title} — {t.amount:.2f} €\n"
        total += t.amount

    text += f"\n────────────\nИтого: {total:.2f} €"

    await message.answer(text)



@dp.message(Command("month"))
async def month(message: Message):

    transactions, income, expense = await get_month_summary()

    if not transactions:
        await message.answer("За этот месяц операций нет.")
        return

    text = "📅 Этот месяц\n\n"

    for t in transactions:

        if t.type == "expense":
            text += f"{t.category} {t.title} — {t.amount:.2f} €\n"

    text += "\n────────────────\n\n"

    text += f"📉 Расходы: {expense:.2f} €\n"
    text += f"📈 Доходы: {income:.2f} €\n"
    text += f"💰 Баланс: {income-expense:.2f} €"

    await message.answer(text)

    async def main():
    print("🚀 Family Budget AI started")
        await dp.start_polling(bot)
        "👋 Привет!\n\n"
        "Я Family Budget AI.\n\n"
        "Напиши, например:\n"
        "Кофе 3.50"
    )

@dp.message()
async def any_message(message: Message):

    result = parse_message(message.text)

    if result is None:
        await message.answer("❌ Не понял сообщение.")
        return

    await save_transaction(result)

    if result["type"] == "expense":
        await message.answer(
            f"""✅ Расход сохранён

{result['category']}

Название: {result['title']}

Сумма: {result['amount']:.2f} €"""
        )
    else:
        await message.answer(
            f"""✅ Доход сохранён

Источник: {result['title']}

Сумма: {result['amount']:.2f} €"""
        )


async def main():
    print("🚀 Family Budget AI started")
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())