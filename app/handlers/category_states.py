from aiogram.fsm.state import State, StatesGroup


class CategorySettingsState(StatesGroup):
    waiting_for_keyword = State()
    waiting_for_custom_name = State()
    waiting_for_custom_icon = State()
    waiting_for_custom_keywords = State()
    waiting_for_edit_name = State()
    waiting_for_edit_icon = State()
