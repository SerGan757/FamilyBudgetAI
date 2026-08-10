from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import t


class GoalCallback(CallbackData, prefix="goal"):
    action: str
    goal_id: int = 0


def _button(text: str, action: str, goal_id: int = 0):
    return InlineKeyboardButton(
        text=text, callback_data=GoalCallback(action=action, goal_id=goal_id).pack(),
    )


def empty_goal_keyboard(language: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_button(t(language, "goal.create"), "create")],
        [_button(t(language, "nav.back"), "back")],
    ])


def goal_keyboard(goal_id: int, language: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_button(t(language, "goal.edit"), "edit", goal_id)],
        [_button(t(language, "goal.complete"), "confirm_complete", goal_id)],
        [_button(t(language, "goal.delete"), "confirm_delete", goal_id)],
        [_button(t(language, "goal.delete_last"), "confirm_delete_last", goal_id)],
        [_button(t(language, "nav.back"), "back")],
    ])


def goal_edit_keyboard(goal_id: int, language: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_button(t(language, "goal.edit_name"), "edit_name", goal_id)],
        [_button(t(language, "goal.edit_amount"), "edit_amount", goal_id)],
        [_button(t(language, "goal.edit_deadline"), "edit_deadline", goal_id)],
        [_button(t(language, "nav.back"), "show", goal_id)],
    ])


def goal_edit_deadline_keyboard(goal_id: int, language: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_button(t(language, "goal.enter_new_deadline"), "enter_edit_deadline", goal_id)],
        [_button(t(language, "goal.no_deadline"), "clear_deadline", goal_id)],
        [_button(t(language, "nav.back"), "edit", goal_id)],
    ])


def goal_edit_cancel_keyboard(goal_id: int, language: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_button(t(language, "goal.cancel"), "edit", goal_id)],
    ])


def deadline_keyboard(language: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_button(t(language, "goal.set_deadline"), "deadline")],
        [_button(t(language, "goal.skip_deadline"), "skip_deadline")],
        [_button(t(language, "goal.cancel"), "cancel")],
    ])


def confirm_keyboard(action: str, goal_id: int, language: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_button(t(language, "goal.confirm"), action, goal_id)],
        [_button(t(language, "goal.cancel"), "show", goal_id)],
    ])
