from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import t


class UndoOperationCallback(CallbackData, prefix="undo_op"):
    kind: str
    operation_id: int


class UndoBatchCallback(CallbackData, prefix="undo_batch"):
    first_id: int
    last_id: int
    signature: str


def undo_batch_keyboard(first_id: int, last_id: int, signature: str,
                        language: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=t(language, "undo.batch_button"),
            callback_data=UndoBatchCallback(
                first_id=first_id, last_id=last_id, signature=signature,
            ).pack(),
        )
    ]])


def undo_operation_keyboard(kind: str, operation_id: int, language: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=t(language, "undo.button"),
            callback_data=UndoOperationCallback(kind=kind, operation_id=operation_id).pack(),
        )
    ]])
