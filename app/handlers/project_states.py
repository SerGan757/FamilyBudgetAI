from aiogram.fsm.state import State, StatesGroup


class ProjectState(StatesGroup):
    waiting_for_name = State()
    waiting_for_tag = State()
    waiting_for_rename = State()
    waiting_for_retag = State()


class ProjectTransactionState(StatesGroup):
    waiting_for_resolution = State()
