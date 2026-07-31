from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.handlers.user_states import RegistrationState
from app.keyboards.main_menu import main_menu
from app.services.expense_service import save_transaction
from app.services.user_service import create_user


router = Router()


@router.message(RegistrationState.waiting_for_group_name)
async def finish_group_registration(
    message: Message,
    state: FSMContext,
):
    """Register a new user and save each pending operation exactly once."""
    if message.text is None:
        return

    name = message.text.strip()
    data = await state.get_data()
    pending_operation_text = data.get("pending_operation_text")
    telegram_id = message.from_user.id

    await create_user(
        telegram_id=telegram_id,
        name=name,
    )
    await state.clear()

    if not pending_operation_text:
        await message.answer(
            f"✅ {name}, регистрация завершена.",
            reply_markup=main_menu,
        )
        return

    saved = []
    failed = []
    income = 0.0
    expense = 0.0

    for line in pending_operation_text.splitlines():
        line = line.strip()
        if not line:
            continue

        result = await save_transaction(line, telegram_id)
        if isinstance(result, str):
            failed.append(line)
            continue

        saved.append(result)
        if result.type == "income":
            income += result.amount
        else:
            expense += result.amount

    text = f"✅ Добро пожаловать, <b>{name}</b>!\n\n"

    if saved:
        text += f"Сохранено операций: <b>{len(saved)}</b>\n\n"
        for transaction in saved:
            sign = "+" if transaction.type == "income" else "-"
            text += (
                f"• {transaction.category} | {transaction.title} | "
                f"{sign}{transaction.amount:.2f} €\n"
            )
        text += f"\n💰 Доходы: {income:.2f} €\n💸 Расходы: {expense:.2f} €"

    if failed:
        text += "\n\n⚠️ Не удалось распознать:\n"
        for line in failed:
            text += f"• {line}\n"

    await message.answer(text, reply_markup=main_menu)
