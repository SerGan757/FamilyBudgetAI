from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from html import escape

from app.handlers.user_states import RegistrationState
from app.handlers.project_states import ProjectTransactionState
from app.keyboards.projects import pending_project_keyboard
from app.keyboards.main_menu import main_menu
from app.services.expense_service import PendingProjectTransaction, save_transaction
from app.services.family_context_service import require_family_for_chat
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
    family_id = data.get("registration_family_id")
    registration_chat_id = data.get("registration_chat_id")
    telegram_id = message.from_user.id

    family = await require_family_for_chat(message.chat.id)
    if (
        family_id is None
        or registration_chat_id != message.chat.id
        or family.id != family_id
    ):
        await state.clear()
        await message.answer("Регистрация была начата в другом чате. Начните заново.")
        return

    await create_user(
        telegram_id=telegram_id,
        name=name,
        family_id=family_id,
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

        result = await save_transaction(line, telegram_id, family_id)
        if isinstance(result, PendingProjectTransaction):
            await state.update_data(
                pending_project_chat_id=message.chat.id,
                pending_project_family_id=family_id,
                pending_project_parsed=result.parsed,
                pending_project_tag=result.tag,
            )
            await state.set_state(ProjectTransactionState.waiting_for_resolution)
            if result.status == "inactive":
                pending_text = f"⚠️ Проект «{escape(result.project.name)}» завершён."
                suggestion = None
            else:
                pending_text = f"⚠️ Проект #{escape(result.tag)} не найден."
                suggestion = result.suggestion
                if suggestion is not None:
                    pending_text += (
                        "\n\nВозможно, вы имели в виду:\n"
                        f"🏷 #{escape(suggestion.tag)} — {escape(suggestion.name)}"
                    )
            await message.answer(
                pending_text, reply_markup=pending_project_keyboard(suggestion),
            )
            return
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
