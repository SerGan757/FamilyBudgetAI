from aiogram.fsm.state import State, StatesGroup

class DocumentState(StatesGroup):
    category_name = State(); category_emoji = State(); title = State(); owner = State()
    custom_owner = State(); access = State(); files = State()
    search = State(); rename = State()
