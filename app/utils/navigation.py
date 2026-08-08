from aiogram.types import InlineKeyboardMarkup, Message

async def answer_with_navigation(
    message: Message,
    text: str,
    *,
    inline_markup: InlineKeyboardMarkup,
    **kwargs,
) -> Message:
    # Telegram allows only one reply_markup per message.  Sending an inline
    # keyboard does not remove the persistent chat-level ReplyKeyboard that
    # was installed by an earlier normal message/menu.
    return await message.answer(text, reply_markup=inline_markup, **kwargs)
