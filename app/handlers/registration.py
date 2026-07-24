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

    name = message.text.strip()

    data = await state.get_data()

    original_text = data.get("original_text")

    telegram_id = message.from_user.id

    await create_user(
        telegram_id=telegram_id,
        name=name,
    )

    await state.clear()

    if not original_text:

        await message.answer(
            f"✅ {name}, регистрация завершена.",
            reply_markup=main_menu,
        )
        return

    saved = []
    failed = []

    income = 0
    expense = 0

    if original_text:

        test = original_text.strip()

        result = await save_transaction(
            test,
            telegram_id,
        )

    if result == "PARSE_ERROR":

        await message.answer(
            f"✅ Добро пожаловать, <b>{name}</b>!",
            reply_markup=main_menu,
        )

        return

    for line in original_text.splitlines():

        line = line.strip()

        if not line:
            continue

        result = await save_transaction(
            line,
            telegram_id,
        )

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

        text += (
            f"Сохранено операций: <b>{len(saved)}</b>\n\n"
        )

        for t in saved:

            sign = "+" if t.type == "income" else "-"

            text += (
                f"• {t.category} | "
                f"{t.title} | "
                f"{sign}{t.amount:.2f} €\n"
            )

        text += (
            f"\n💰 Доходы: {income:.2f} €"
            f"\n💸 Расходы: {expense:.2f} €"
        )

    if failed:

        text += "\n\n⚠️ Не удалось распознать:\n"

        for line in failed:
            text += f"• {line}\n"

    await message.answer(
        text,
        reply_markup=main_menu,
    )