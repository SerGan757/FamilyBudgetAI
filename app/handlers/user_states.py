from aiogram.fsm.state import State, StatesGroup


class RegistrationState(StatesGroup):

    # Регистрация через личный чат (/start)
    waiting_for_name = State()

    # Регистрация нового пользователя прямо в группе
    waiting_for_group_name = State()