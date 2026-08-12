from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import t


class UndoOperationCallback(CallbackData, prefix="undo_op"):
    kind: str
    operation_id: int


def undo_operation_keyboard(kind: str, operation_id: int, language: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=t(language, "undo.button"),
            callback_data=UndoOperationCallback(kind=kind, operation_id=operation_id).pack(),
        )
    ]])
