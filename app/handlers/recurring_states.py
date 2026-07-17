from aiogram.fsm.state import State, StatesGroup


class RecurringState(StatesGroup):
    waiting_for_payment = State()