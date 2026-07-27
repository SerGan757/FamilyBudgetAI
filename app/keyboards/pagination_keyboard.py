from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)


def pagination_keyboard(
    prefix: str,
    offset: int,
    total: int,
    limit: int = 20,
) -> InlineKeyboardMarkup:

    keyboard = []

    row = []

    if offset > 0:
        row.append(
            InlineKeyboardButton(
                text="⬅️ Предыдущие 20",
                callback_data=f"{prefix}:{max(0, offset-limit)}",
            )
        )

    if offset + limit < total:
        row.append(
            InlineKeyboardButton(
                text="➡️ Следующие 20",
                callback_data=f"{prefix}:{offset+limit}",
            )
        )

    if row:
        keyboard.append(row)

    return InlineKeyboardMarkup(
        inline_keyboard=keyboard
    )