from datetime import datetime
from html import escape

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.handlers.savings_goal_states import SavingsGoalState
from app.i18n import family_language, month_name, t
from app.keyboards.savings_goal import (
    GoalCallback, confirm_keyboard, deadline_keyboard, empty_goal_keyboard, goal_keyboard,
)
from app.keyboards.settings_menu import family_settings_keyboard_for_ttl
from app.services.family_context_service import require_family_for_chat
from app.services.savings_goal_service import (
    complete_goal, create_goal, delete_goal, delete_last_contribution,
    get_goal_snapshot, progress_bar, update_goal,
)
from app.utils.currency import family_currency, format_money

router = Router()


def goal_card(snapshot, currency: str, language: str) -> str:
    goal = snapshot.goal
    lines = [
        f"🎯 <b>{t(language, 'goal.title')}: {escape(goal.name)}</b>", "",
        f"🏦 {t(language, 'goal.saved')}: {format_money(snapshot.saved, currency)} / {format_money(goal.target_amount, currency)}",
        progress_bar(snapshot.saved, goal.target_amount),
    ]
    if snapshot.remaining > 0:
        lines.append(f"💰 {t(language, 'goal.remaining')}: {format_money(snapshot.remaining, currency)}")
    else:
        lines.append(f"🎉 {t(language, 'goal.reached')}")
    if goal.deadline:
        lines.append(f"📅 {t(language, 'goal.deadline')}: {goal.deadline:%d.%m.%Y}")
    return "\n".join(lines)


async def _context(event):
    message = event.message if isinstance(event, CallbackQuery) else event
    user = event.from_user
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type, telegram_id=user.id,
    )
    return message, family, family_language(family)


async def _show(message, family, language):
    snapshot = await get_goal_snapshot(family.id)
    if snapshot is None:
        await message.edit_text(
            f"🎯 <b>{t(language, 'goal.settings_title')}</b>\n\n{t(language, 'goal.not_configured')}",
            reply_markup=empty_goal_keyboard(language), parse_mode="HTML",
        )
    else:
        await message.edit_text(
            goal_card(snapshot, family_currency(family), language),
            reply_markup=goal_keyboard(snapshot.goal.id, language), parse_mode="HTML",
        )


@router.callback_query(GoalCallback.filter())
async def goal_callback(callback: CallbackQuery, callback_data: GoalCallback, state: FSMContext):
    message, family, language = await _context(callback)
    action, goal_id = callback_data.action, callback_data.goal_id
    if action == "back":
        await state.clear()
        from app.handlers.settings import family_settings_text
        from app.services.settings_service import get_family_settings_data
        data = await get_family_settings_data(family.id)
        await message.edit_text(
            family_settings_text(data),
            reply_markup=family_settings_keyboard_for_ttl(data["temporary_screen_ttl"], language),
            parse_mode="HTML",
        )
    elif action in {"show", "cancel"}:
        await state.clear()
        await _show(message, family, language)
    elif action in {"create", "edit"}:
        snapshot = await get_goal_snapshot(family.id)
        if action == "create" and snapshot is not None:
            await callback.answer(t(language, "goal.only_one"), show_alert=True)
            return
        await state.set_state(SavingsGoalState.waiting_for_name)
        await state.update_data(goal_family_id=family.id, goal_edit_id=goal_id if action == "edit" else 0)
        await message.edit_text(t(language, "goal.enter_name"))
    elif action == "choose_deadline":
        await message.edit_text(t(language, "goal.deadline_optional"), reply_markup=deadline_keyboard(language))
    elif action == "deadline":
        await state.set_state(SavingsGoalState.waiting_for_deadline)
        await message.edit_text(t(language, "goal.enter_deadline"))
    elif action == "skip_deadline":
        await _save_from_state(message, state, family, language, None)
    elif action in {"confirm_complete", "confirm_delete", "confirm_delete_last"}:
        target = action.removeprefix("confirm_")
        await message.edit_text(
            t(language, f"goal.confirm_{target}"),
            reply_markup=confirm_keyboard(target, goal_id, language),
        )
    elif action == "complete":
        await complete_goal(family.id, goal_id)
        await _show(message, family, language)
    elif action == "delete":
        await delete_goal(family.id, goal_id)
        await _show(message, family, language)
    elif action == "delete_last":
        await delete_last_contribution(family.id, goal_id)
        await _show(message, family, language)
    await callback.answer()


@router.message(SavingsGoalState.waiting_for_name)
async def goal_name(message: Message, state: FSMContext):
    family = await require_family_for_chat(message.chat.id, chat_type=message.chat.type, telegram_id=message.from_user.id)
    language = family_language(family)
    name = (message.text or "").strip()
    if not name or len(name) > 100:
        await message.answer(t(language, "goal.invalid_name"))
        return
    await state.update_data(goal_name=name)
    await state.set_state(SavingsGoalState.waiting_for_amount)
    await message.answer(t(language, "goal.enter_amount"))


@router.message(SavingsGoalState.waiting_for_amount)
async def goal_amount(message: Message, state: FSMContext):
    family = await require_family_for_chat(message.chat.id, chat_type=message.chat.type, telegram_id=message.from_user.id)
    language = family_language(family)
    try:
        amount = float((message.text or "").strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer(t(language, "goal.invalid_amount"))
        return
    await state.update_data(goal_amount=amount)
    await message.answer(t(language, "goal.deadline_optional"), reply_markup=deadline_keyboard(language))


@router.message(SavingsGoalState.waiting_for_deadline)
async def goal_deadline(message: Message, state: FSMContext):
    family = await require_family_for_chat(message.chat.id, chat_type=message.chat.type, telegram_id=message.from_user.id)
    language = family_language(family)
    try:
        deadline = datetime.strptime((message.text or "").strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer(t(language, "goal.invalid_deadline"))
        return
    await _save_from_state(message, state, family, language, deadline)


async def _save_from_state(message: Message, state: FSMContext, family, language: str, deadline):
    data = await state.get_data()
    edit_id = int(data.get("goal_edit_id") or 0)
    if edit_id:
        goal = await update_goal(family.id, edit_id, data["goal_name"], data["goal_amount"], deadline)
    else:
        try:
            goal = await create_goal(family.id, data["goal_name"], data["goal_amount"], deadline)
        except ValueError:
            await state.clear()
            await message.answer(t(language, "goal.only_one"))
            return
    await state.clear()
    snapshot = await get_goal_snapshot(family.id)
    await message.answer(
        goal_card(snapshot, family_currency(family), language),
        reply_markup=goal_keyboard(goal.id, language), parse_mode="HTML",
    )
