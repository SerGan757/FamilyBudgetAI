import re
from html import escape

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.handlers.user_states import RegistrationState
from app.handlers.project_states import ProjectTransactionState
from app.keyboards.projects import PendingProjectCallback, pending_project_keyboard
from app.keyboards.main_menu import back_to_main_menu_keyboard
from app.services.family_context_service import (
    FamilyContextConflictError,
    FamilyContextNotFoundError,
    get_or_create_family_for_chat,
    require_family_for_chat,
)
from app.services.expense_service import (
    PendingProjectTransaction, create_transaction, save_transaction,
)
from app.services.project_service import get_project
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
    try:
        family = await require_family_for_chat(
            message.chat.id,
            chat_type=message.chat.type,
            telegram_id=message.from_user.id,
        )
    except FamilyContextNotFoundError:
        if message.chat.type == "private":
            await message.answer(
                "Вы ещё не подключены к семейному бюджету.\n"
                "Нажмите /start, чтобы создать бюджет или присоединиться к семье."
            )
        else:
            await message.answer("⚠️ Для этого чата не настроен семейный контекст.")
        return
    user = await get_user_by_telegram_id(
        telegram_id
    )

    if user is not None and user.family_id != family.id:
        await message.answer(
            "Вы уже зарегистрированы в другой семье.\n"
            "Поддержка участия одного пользователя в нескольких семьях "
            "будет добавлена на следующем этапе."
        )
        return

    if user is None:

        chat_title = message.chat.title or f"Личный бюджет {message.from_user.full_name}"
        try:
            family = await get_or_create_family_for_chat(message.chat.id, chat_title)
        except FamilyContextConflictError:
            await message.answer(
                "⚠️ Для этого чата требуется явная привязка существующей семьи."
            )
            return

        await state.set_state(
            RegistrationState.waiting_for_group_name
        )

        await state.update_data(
            pending_operation_text=message.text,
            registration_family_id=family.id,
            registration_chat_id=message.chat.id,
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
            family.id,
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

        if isinstance(result, PendingProjectTransaction):
            await state.update_data(
                pending_project_chat_id=message.chat.id,
                pending_project_family_id=family.id,
                pending_project_parsed=result.parsed,
                pending_project_tag=result.tag,
            )
            await state.set_state(ProjectTransactionState.waiting_for_resolution)
            if result.status == "inactive":
                text = f"⚠️ Проект «{escape(result.project.name)}» завершён."
                suggestion = None
            else:
                text = f"⚠️ Проект #{result.tag} не найден."
                suggestion = result.suggestion
                if suggestion is not None:
                    text += (
                        "\n\nВозможно, вы имели в виду:\n"
                        f"🏷 #{escape(suggestion.tag)} — {escape(suggestion.name)}"
                    )
            await message.answer(
                text, reply_markup=pending_project_keyboard(suggestion),
            )
            return

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
        )

        for transaction in saved:
            project_name = getattr(transaction, "project_name", None)
            if project_name:
                text += f"🏷 Проект: {escape(str(project_name))}\n"

        text += "══════════════════════════════\n\n"

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


@router.callback_query(
    ProjectTransactionState.waiting_for_resolution,
    PendingProjectCallback.filter(),
)
async def resolve_pending_project_transaction(
    callback: CallbackQuery,
    callback_data: PendingProjectCallback,
    state: FSMContext,
):
    data = await state.get_data()
    message = callback.message
    user = await get_user_by_telegram_id(callback.from_user.id)
    family_id = data.get("pending_project_family_id")
    parsed = data.get("pending_project_parsed")
    if (
        message is None
        or user is None
        or user.family_id != family_id
        or message.chat.id != data.get("pending_project_chat_id")
        or not isinstance(parsed, dict)
    ):
        await state.clear()
        await callback.answer("Сценарий недействителен.", show_alert=True)
        return

    if callback_data.action == "cancel":
        await state.clear()
        await message.edit_text("❌ Операция отменена.")
        await callback.answer()
        return

    project_id = None
    project_name = None
    if callback_data.action == "select":
        project = await get_project(callback.from_user.id, callback_data.project_id)
        if project is None or not project.is_active:
            await state.clear()
            await callback.answer("Проект недоступен.", show_alert=True)
            return
        project_id = project.id
        project_name = getattr(project, "name", None)
    elif callback_data.action != "without":
        await callback.answer("Неизвестное действие.", show_alert=True)
        return

    transaction = await create_transaction(
        user_id=user.id,
        family_id=family_id,
        title=parsed["title"],
        amount=parsed["amount"],
        transaction_type=parsed["type"],
        category=parsed["category"],
        project_id=project_id,
    )
    await state.clear()
    sign = "+" if transaction.type == "income" else "-"
    project_header = (
        f"🏷 Проект: {escape(str(project_name))}\n\n" if project_name else ""
    )
    await message.edit_text(
        f"✅ Операция сохранена.\n{project_header}"
        f"{escape(transaction.title)} · {sign}{transaction.amount:.2f} €"
    )
    await callback.answer()
