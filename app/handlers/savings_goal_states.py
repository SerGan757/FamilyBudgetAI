from aiogram.fsm.state import State, StatesGroup


class SavingsGoalState(StatesGroup):
    waiting_for_name = State()
    waiting_for_amount = State()
    waiting_for_deadline = State()
