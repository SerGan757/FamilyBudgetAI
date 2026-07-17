from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def delete_keyboard(payment_id: int) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=f"rec_delete:{payment_id}",
                )
            ]
        ]
    )