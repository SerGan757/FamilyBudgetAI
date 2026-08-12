from aiogram.fsm.state import State, StatesGroup


class CategorySettingsState(StatesGroup):
    waiting_for_keyword = State()
