from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.services.delete_service import (
    delete_last_transaction,
    delete_transaction_by_id,
)
from app.keyboards.main_menu import main_menu

router = Router()

waiting_for_delete_id = set()


def operation_card(transaction) -> str:

    if transaction.type == "expense":
        icon = transaction.category.split()[0]
        sign = "-"
    else:
        icon = "💰"
        sign = "+"

    return (
        "<pre>"
        "🗑️ Операция удалена\n"
        "──────────────────────\n\n"
        f"ID {transaction.id}\n"
        f"{icon} {transaction.title.capitalize()}\n\n"
        f"{sign} {transaction.amount:.2f} €"
        "</pre>"
    )


@router.message(Command("undo"))
async def undo(message: Message):

    transaction = await delete_last_transaction()

    if transaction is None:
        await message.answer(
            "История пуста.",
            reply_markup=main_menu,
        )
        return

    await message.answer(
        operation_card(transaction),
        reply_markup=main_menu,
    )


@router.message(Command("delete"))
async def delete(message: Message):

    parts = message.text.split()

    if len(parts) != 2:

        await message.answer(
            "Использование:\n"
            "<pre>/delete 125</pre>",
            reply_markup=main_menu,
        )
        return

    try:
        transaction_id = int(parts[1])

    except ValueError:

        await message.answer(
            "ID должен быть числом.",
            reply_markup=main_menu,
        )
        return

    transaction = await delete_transaction_by_id(transaction_id)

    if transaction is None:

        await message.answer(
            f"ID {transaction_id} не найден.",
            reply_markup=main_menu,
        )
        return

    await message.answer(
        operation_card(transaction),
        reply_markup=main_menu,
    )


@router.message(F.text.regexp(r"^\d+$"))
async def delete_from_menu(message: Message):

    if message.from_user.id not in waiting_for_delete_id:
        return

    waiting_for_delete_id.remove(message.from_user.id)

    transaction = await delete_transaction_by_id(int(message.text))

    if transaction is None:

        await message.answer(
            "Такого ID нет.",
            reply_markup=main_menu,
        )
        return

    await message.answer(
        operation_card(transaction),
        reply_markup=main_menu,
    )