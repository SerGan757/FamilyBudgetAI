from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def delete_keyboard(recurring_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=f"delete_recurring:{recurring_id}",
                )
            ]
        ]
    )