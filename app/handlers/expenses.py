import re
from html import escape

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.handlers.user_states import RegistrationState
from app.handlers.project_states import ProjectTransactionState
from app.keyboards.projects import PendingProjectCallback, pending_project_keyboard
from app.keyboards.main_menu import back_to_main_menu
from app.keyboards.undo import UndoOperationCallback, undo_operation_keyboard
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
from app.services.parser import parse_message
from app.services.savings_goal_service import add_contribution, get_goal_snapshot, progress_bar
from app.services.undo_service import undo_recent_operation
from app.utils.currency import family_currency, format_money
from app.i18n import category_label, family_language, normalize_telegram_language, t

router = Router()


def quick_confirmation_text(saved, language: str, currency: str, failed=None) -> str:
    """Build a compact HTML confirmation without code/pre blocks."""
    failed = failed or []
    rows = [f"✅ {t(language, 'quick.saved', count=len(saved))}"] if saved else []
    types = {transaction.type for transaction in saved}
    income_total = sum(transaction.amount for transaction in saved if transaction.type == "income")
    expense_total = sum(transaction.amount for transaction in saved if transaction.type == "expense")

    for transaction in saved:
        sign = "+" if transaction.type == "income" else "-"
        kind = t(language, "quick.income_item" if transaction.type == "income" else "quick.expense_item")
        project_name = getattr(transaction, "project_name", None)
        project = (
            f"   🏷 {t(language, 'quick.project')}: {escape(str(project_name))}"
            if project_name else ""
        )
        rows.append(
            f"{escape(category_label(language, transaction.category))}   "
            f"{escape(transaction.title[:20])}   {kind}   "
            f"{sign}{format_money(transaction.amount, currency)}{project}"
        )

    if "income" in types:
        rows.append(f"💰 {t(language, 'quick.income')}: {format_money(income_total, currency)}")
    if "expense" in types:
        rows.append(f"💸 {t(language, 'quick.expense')}: {format_money(expense_total, currency)}")
    if failed:
        rows.append(t(language, "quick.unrecognized"))
        rows.extend(f"• {escape(line)}" for line in failed)
    return "\n".join(rows)


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
    language = family_language(family)

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
            family = await get_or_create_family_for_chat(
                message.chat.id, chat_title,
                initial_language=normalize_telegram_language(getattr(message.from_user, "language_code", None)),
            )
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
    goal_messages = []

    total_income = 0.0
    total_expense = 0.0

    for line in lines:

        parsed_line = parse_message(line)
        if parsed_line and parsed_line["type"] == "goal_contribution":
            contribution = await add_contribution(
                family.id, telegram_id, parsed_line["amount"],
            )
            if contribution is None:
                goal_messages.append((t(language, "goal.no_active_for_contribution"), None))
                continue
            snapshot = await get_goal_snapshot(family.id)
            goal_messages.append((
                f"✅ {t(language, 'goal.contributed', name=escape(snapshot.goal.name), amount=format_money(contribution.amount, family_currency(family)))}\n\n"
                f"🏦 {t(language, 'goal.saved')}: {format_money(snapshot.saved, family_currency(family))} / {format_money(snapshot.goal.target_amount, family_currency(family))}\n"
                f"{progress_bar(snapshot.saved, snapshot.goal.target_amount)}\n"
                f"💰 {t(language, 'goal.remaining_short')}: {format_money(snapshot.remaining, family_currency(family))}",
                contribution,
            ))
            continue

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
                pending_project_currency=family_currency(family),
                pending_project_language=language,
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

    if goal_messages:
        created_count = len(saved) + sum(contribution is not None for _, contribution in goal_messages)
        only_contribution = goal_messages[0][1] if len(goal_messages) == 1 else None
        markup = (
            undo_operation_keyboard("goal", only_contribution.id, language)
            if created_count == 1 and only_contribution is not None and not failed
            else back_to_main_menu(language)
        )
        await message.answer("\n\n".join(text for text, _ in goal_messages), reply_markup=markup)

    if not saved and not failed:
        return

    text = quick_confirmation_text(
        saved, language, family_currency(family), failed,
    )

    undo_markup = (
        undo_operation_keyboard("transaction", saved[0].id, language)
        if len(saved) == 1 and not goal_messages and not failed
        else back_to_main_menu(language)
    )
    await message.answer(
        text,
        reply_markup=undo_markup,
        parse_mode="HTML",
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
    transaction.project_name = project_name
    await message.edit_text(
        quick_confirmation_text(
            [transaction], data.get("pending_project_language"),
            data.get("pending_project_currency"),
        ),
        reply_markup=undo_operation_keyboard(
            "transaction", transaction.id, data.get("pending_project_language"),
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(UndoOperationCallback.filter())
async def undo_operation_callback(
    callback: CallbackQuery,
    callback_data: UndoOperationCallback,
):
    message = callback.message
    if message is None:
        await callback.answer()
        return
    family = await require_family_for_chat(
        message.chat.id,
        chat_type=message.chat.type,
        telegram_id=callback.from_user.id,
    )
    language = family_language(family)
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None or user.family_id != family.id:
        await callback.answer(t(language, "undo.forbidden"), show_alert=True)
        return

    result = await undo_recent_operation(
        callback_data.kind,
        callback_data.operation_id,
        family.id,
        user.id,
    )
    if result.status == "deleted":
        await message.edit_text(t(language, "undo.done"))
        await callback.answer()
        return
    key = {
        "expired": "undo.expired",
        "already_deleted": "undo.deleted",
        "not_author": "undo.author_only",
    }.get(result.status, "undo.forbidden")
    await callback.answer(t(language, key), show_alert=True)
