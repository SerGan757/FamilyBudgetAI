from aiogram.fsm.context import FSMContext


async def cancel_state(state: FSMContext):

    current = await state.get_state()

    if current is not None:
        await state.clear()