from aiogram.fsm.state import State, StatesGroup


class RecurringState(StatesGroup):
    waiting_for_payment = State()
    waiting_for_edit_payment = State()
