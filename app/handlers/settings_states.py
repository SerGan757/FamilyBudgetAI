from aiogram.fsm.state import State, StatesGroup


class FamilySettingsState(StatesGroup):
    waiting_for_city = State()
