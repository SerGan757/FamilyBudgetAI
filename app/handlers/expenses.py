import re

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.handlers.user_states import RegistrationState
from app.keyboards.main_menu import back_to_main_menu_keyboard
from app.services.expense_service import save_transaction
from app.services.user_service import get_user_by_telegram_id

router = Router()


@router.message(StateFilter(None))
async def add_transaction(
    message: Message,
    state: FSMContext,
):
    print("EXPENSE:", message.from_user.id, message.text)

    if message.text is None:
        return

    lines = [
        line.strip()
        for line in message.text.splitlines()
        if line.strip()
    ]

    if not lines:
        return

    telegram_id = message.from_user.id
    user = await get_user_by_telegram_id(
        telegram_id
    )

    if user is None:

        await state.set_state(
            RegistrationState.waiting_for_group_name
        )

        await state.update_data(
            pending_operation_text=message.text,
        )

        await message.answer(
            "👋 Похоже, мы ещё не знакомы.\n\n"
            "Как тебя зовут?"
        )

        return

    saved = []
    failed = []

    total_income = 0.0
    total_expense = 0.0

    for line in lines:

        result = await save_transaction(
            line,
            telegram_id,
        )

        if result == "PARSE_ERROR":

            # Если в строке нет цифр — считаем это обычным разговором
            # и полностью игнорируем.
            if not re.search(r"\d", line):
                continue

            # Если цифры есть, но операция не распознана —
            # показываем пользователю ошибку.
            failed.append(line)
            continue

        saved.append(result)

        if result.type == "income":
            total_income += result.amount
        else:
            total_expense += result.amount

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
        reply_markup=back_to_main_menu_keyboard,
    )
