from aiogram.types import Message

from app.keyboards.main_menu import back_to_main_menu_keyboard


async def show_back_keyboard(message: Message) -> None:
    await message.answer("\u2063", reply_markup=back_to_main_menu_keyboard)
