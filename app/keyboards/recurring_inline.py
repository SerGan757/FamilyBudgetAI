from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import t


def delete_keyboard(recurring_id: int, language: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(language, "recurring.delete"),
                    callback_data=f"rec_delete:{recurring_id}",
                )
            ]
        ]
    )
