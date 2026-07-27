from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)


def history_keyboard(
    offset: int,
    total: int,
    limit: int = 20,
) -> InlineKeyboardMarkup:

    buttons = []

    row = []

    if offset > 0:
        row.append(
            InlineKeyboardButton(
                text="⬅️ Предыдущие 20",
                callback_data=f"history:{offset-limit}",
            )
        )

    if offset + limit < total:
        row.append(
            InlineKeyboardButton(
                text="➡️ Следующие 20",
                callback_data=f"history:{offset+limit}",
            )
        )

    if row:
        buttons.append(row)

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )