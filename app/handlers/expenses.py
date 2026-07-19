from aiogram import Router
from aiogram.types import Message

from app.keyboards.main_menu import main_menu
from app.services.expense_service import save_transaction

router = Router()


@router.message()
async def add_transaction(message: Message):

    if message.text is None:
        return

    print(
        f"EXPENSE: chat={message.chat.type}, text={message.text}"
    )

    lines = [
        line.strip()
        for line in message.text.splitlines()
        if line.strip()
    ]

    saved = []
    failed = []

    total_income = 0.0
    total_expense = 0.0

    telegram_id = message.from_user.id

    for line in lines:

        transaction = await save_transaction(
            line,
            telegram_id,
        )

        if transaction is None:
            failed.append(line)
            continue

        saved.append(transaction)

        if transaction.type == "income":
            total_income += transaction.amount
        else:
            total_expense += transaction.amount

    if not saved and not failed:
        return

    text = "<pre>"

    if saved:

        text += (
            f"✅ Сохранено операций: {len(saved)}\n"
            "══════════════════════════════\n\n"
        )

        for t in saved:

            sign = "+" if t.type == "income" else "-"

            text += (
                f"{t.category:<18}"
                f"{t.title[:20]:<20}"
                f"{sign}{t.amount:>8.2f} €\n"
            )

        text += (
            "\n──────────────────────────────\n"
            f"💰 Доходы : {total_income:.2f} €\n"
            f"💸 Расходы: {total_expense:.2f} €\n"
        )

    if failed:

        text += (
            "\n══════════════════════════════\n"
            "⚠️ Не распознано:\n\n"
        )

        for line in failed:
            text += f"• {line}\n"

    text += "</pre>"

    await message.answer(
        text,
        reply_markup=main_menu,
    )