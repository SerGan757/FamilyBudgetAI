from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from app.i18n import t


def pagination_keyboard(
    prefix: str,
    offset: int,
    total: int,
    limit: int = 20,
    language: str = "ru",
) -> InlineKeyboardMarkup:

    keyboard = []

    row = []

    if offset > 0:
        row.append(
            InlineKeyboardButton(
                text=t(language, "nav.prev_20"),
                callback_data=f"{prefix}:{max(0, offset-limit)}",
            )
        )

    if offset + limit < total:
        row.append(
            InlineKeyboardButton(
                text=t(language, "nav.next_20"),
                callback_data=f"{prefix}:{offset+limit}",
            )
        )

    if row:
        keyboard.append(row)

    return InlineKeyboardMarkup(
        inline_keyboard=keyboard
    )
