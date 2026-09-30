from aiogram import BaseMiddleware
from aiogram.filters import Command

from app.handlers.document_states import DocumentState
from app.i18n import all_texts
from app.i18n.translations import SUPPORTED_LANGUAGES
from app.keyboards.main_menu import back_to_main_menu, main_menu_keyboard
from app.services.parser import is_financial_handoff


# The rendered keyboards are the source of truth, including every locale.
NAVIGATION_TEXTS = frozenset(
    button.text
    for language in SUPPORTED_LANGUAGES
    for keyboard in (main_menu_keyboard(language), back_to_main_menu(language))
    for row in keyboard.keyboard
    for button in row
) | all_texts("menu.balance") | all_texts("menu.documents") | {"➕ Добавить"}
NAVIGATION_COMMAND = Command("start", "menu", "history", "today", "month", "balance", "analytics")


class DocumentNavigationMiddleware(BaseMiddleware):
    """Exit Documents before routing the same message to its destination.

    Uploads are already persisted; clearing this UI session needs no commit
    or deletion. Done is optional. Recognized financial text may also leave
    after a successful file save; ambiguous text stays in the upload flow.
    """

    async def __call__(self, handler, event, data):
        state = data.get("state")
        if event.text and state is not None and data.get("raw_state") in DocumentState.__all_states_names__:
            should_leave = event.text in NAVIGATION_TEXTS or await NAVIGATION_COMMAND(event, data["bot"])
            if not should_leave and data["raw_state"] == DocumentState.files.state:
                upload = await state.get_data()
                should_leave = (
                    bool(upload.get("upload_session_key"))
                    and upload.get("document_id") is not None
                    and upload.get("file_count", 0) > 0
                    and is_financial_handoff(event.text)
                )
            if should_leave:
                await state.clear()
                # FSM middleware cached this before message routing.
                data["raw_state"] = None
        return await handler(event, data)
