from aiogram.types import InlineKeyboardMarkup, Message

from app.keyboards.main_menu import back_to_main_menu_keyboard


async def answer_with_navigation(
    message: Message,
    text: str,
    *,
    inline_markup: InlineKeyboardMarkup,
    **kwargs,
) -> Message:
    sent_message = await message.answer(
        text, reply_markup=back_to_main_menu_keyboard, **kwargs,
    )
    await sent_message.edit_reply_markup(reply_markup=inline_markup)
    return sent_message
