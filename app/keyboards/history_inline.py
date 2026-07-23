from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)


def history_keyboard(transaction_id: int) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=f"hist_delete:{transaction_id}",
                ),
                InlineKeyboardButton(
                    text="✏️ Изменить",
                    callback_data=f"hist_edit:{transaction_id}",
                ),
            ]
        ]
    )