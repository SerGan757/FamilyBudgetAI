import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram import Bot, Dispatcher, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.dispatcher.event.handler import HandlerObject
from aiogram.methods import EditMessageText
from aiogram.types import Chat, Message, Update, User

from app.handlers import documents, expenses, menu, routers, settings
from app.handlers.document_navigation import DocumentNavigationMiddleware
from app.handlers.document_states import DocumentState
from app.i18n import t
from app.i18n.translations import SUPPORTED_LANGUAGES
from app.keyboards.documents import DocumentCallback
from app.keyboards.main_menu import main_menu_keyboard


class DocumentsFSMTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = Bot("123456:TEST")
        self.dp = Dispatcher()
        self.dp.message.outer_middleware(DocumentNavigationMiddleware())
        self.destinations = {}
        # Preserve production ordering and filters; isolate destination side effects.
        for original in routers:
            clone = Router()
            for registered in original.message.handlers:
                callback = registered.callback
                if original is not documents.router:
                    callback = AsyncMock(return_value=registered.callback.__name__)
                    callback.aiogram_flag = {}
                    self.destinations[registered.callback.__name__] = callback
                clone.message.handlers.append(HandlerObject(callback=callback, filters=registered.filters))
            self.dp.include_router(clone)
        self.state = self.dp.fsm.get_context(bot=self.bot, chat_id=10, user_id=10)
        self.panel = SimpleNamespace(chat=SimpleNamespace(id=10), message_id=500,
                                     edit_text=AsyncMock(), answer=AsyncMock())
        self.callback = SimpleNamespace(message=self.panel, from_user=SimpleNamespace(id=10), answer=AsyncMock())
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(documents, "_lang", AsyncMock(return_value="ru")))
        self.store = self.stack.enter_context(patch.object(documents, "create_or_append_document_file", AsyncMock(
            return_value=SimpleNamespace(document=SimpleNamespace(id=77), file_count=1, file_added=True))))
        self.get = self.stack.enter_context(patch.object(documents, "get_document", AsyncMock(return_value=SimpleNamespace(id=77))))
        self.delete = self.stack.enter_context(patch.object(documents, "delete_document", AsyncMock()))
        self.stack.enter_context(patch.object(documents, "schedule_temporary_message", AsyncMock()))
        self.answer = self.stack.enter_context(patch.object(Message, "answer", AsyncMock(return_value=self.panel)))

    async def asyncTearDown(self):
        self.stack.close()
        await self.dp.storage.close()
        await self.bot.session.close()

    async def active(self, current=DocumentState.files):
        await self.state.set_state(current)
        await self.state.set_data(dict(category_id=7, title="Passport", owner="Me", access_level="private",
                                       upload_session_key="session-key"))

    async def action(self, action):
        await documents.document_callback(self.callback, SimpleNamespace(action=action, value=7), self.state)

    async def send(self, text):
        message = Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=10, type="private"),
                          from_user=User(id=10, is_bot=False, first_name="Test"), text=text)
        return await self.dp.feed_update(self.bot, Update(update_id=1, message=message))

    async def photo(self, file_id="file"):
        message = SimpleNamespace(from_user=SimpleNamespace(id=10), text=None, document=None,
            photo=[SimpleNamespace(file_id=file_id, file_unique_id=f"unique-{file_id}")],
            answer=AsyncMock(return_value=self.panel), bot=SimpleNamespace(edit_message_text=AsyncMock()))
        await documents.receive_file(message, self.state)
        return message

    async def uploaded_files(self, count=4):
        """Model committed service results without connecting to PostgreSQL."""
        await self.action("new_document")
        await self.send("Passport")
        await self.action("owner_me")
        await self.action("access_private")
        self.callback.answer.reset_mock()
        self.answer.reset_mock()
        saved = SimpleNamespace(id=77, files=[])

        async def append_file(uid, key, category_id, title, owner, access, item):
            saved.files.append(dict(item))
            return SimpleNamespace(document=saved, file_count=len(saved.files), file_added=True)

        self.store.side_effect = append_file
        self.get.return_value = saved
        for index in range(count):
            message = await self.photo(f"file-{index}")
        self.assertEqual(await self.state.get_state(), DocumentState.files.state)
        self.assertEqual((await self.state.get_data())["file_count"], count)
        if count == 1:
            panel_text = message.answer.await_args.args[0]
            panel_update = message.answer.await_args.kwargs
        else:
            panel_update = message.bot.edit_message_text.await_args.kwargs
            panel_text = panel_update["text"]
        self.assertIn(t("ru", "documents.files", count=count), panel_text)
        self.assertEqual(
            [DocumentCallback.unpack(button.callback_data).action
             for row in panel_update["reply_markup"].inline_keyboard for button in row],
            ["add_file", "done", "delete_draft_document"],
        )
        return saved

    async def test_four_documents_full_lifecycle_and_done(self):
        for index in range(4):
            await self.action("new_document")
            self.assertEqual(await self.state.get_state(), DocumentState.title.state)
            await self.send(f"Document {index}")
            await self.action("owner_me")
            await self.action("access_private")
            await self.photo()
            await self.action("add_file")
            self.assertIsNotNone(self.panel.edit_text.await_args.kwargs["reply_markup"])
            await self.photo()
            await self.action("done")
            self.assertIsNone(await self.state.get_state())
            self.assertEqual(await self.state.get_data(), {})
        self.assertEqual(self.store.await_count, 8)
        self.assertEqual(await self.send(t("ru", "menu.settings")), "open_settings")
        self.assertEqual(await self.send("кофе 3"), "add_transaction")

    async def test_active_text_stays_in_upload_without_expense(self):
        await self.active()
        await self.send("кофе 3")
        self.answer.assert_awaited_once_with(t("ru", "documents.upload_prompt"))
        self.destinations["add_transaction"].assert_not_awaited()
        self.store.assert_not_awaited()
        self.assertEqual(await self.state.get_state(), DocumentState.files.state)

    async def test_first_file_done_clears_session(self):
        await self.active()
        await self.photo()
        await self.action("done")
        self.assertIsNone(await self.state.get_state())
        self.assertEqual(await self.state.get_data(), {})

    async def test_text_after_saved_files_stays_in_upload(self):
        saved = await self.uploaded_files()
        saved_files = [dict(item) for item in saved.files]
        await self.send("кофе 3")
        self.answer.assert_awaited_once_with(t("ru", "documents.upload_prompt"))
        self.destinations["add_transaction"].assert_not_awaited()
        self.assertEqual(await self.state.get_state(), DocumentState.files.state)
        self.assertEqual(self.store.await_count, 4)
        self.assertEqual(saved.files, saved_files)
        self.delete.assert_not_awaited()

    async def test_photo_caption_does_not_act_as_global_navigation(self):
        await self.active()
        message = Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=10, type="private"),
            from_user=User(id=10, is_bot=False, first_name="Test"), caption="/start",
            photo=[dict(file_id="file", file_unique_id="unique", width=100, height=100)])
        handler = AsyncMock()
        data = dict(state=self.state, raw_state=DocumentState.files.state, bot=self.bot)
        await DocumentNavigationMiddleware()(handler, message, data)
        self.assertEqual(await self.state.get_state(), DocumentState.files.state)
        handler.assert_awaited_once_with(message, data)

    async def test_global_buttons_cover_all_documents_states_and_languages(self):
        destinations = {"settings":"open_settings", "history":"history_menu", "today":"today_menu",
                        "month":"month_menu", "analytics":"analytics_menu", "recurring":"recurring",
                        "year":"year_menu", "delete":"delete"}
        for language in SUPPORTED_LANGUAGES:
            self.assertEqual(
                {button.text for row in main_menu_keyboard(language).keyboard for button in row},
                {t(language, f"menu.{key}") for key in destinations},
            )
        for current in DocumentState.__all_states__:
            languages = SUPPORTED_LANGUAGES if current == DocumentState.files else ("ru",)
            for language in languages:
                for key, handler in destinations.items():
                    with self.subTest(state=current, language=language, key=key):
                        await self.active(current)
                        self.assertEqual(await self.send(t(language, f"menu.{key}")), handler)
                        self.assertIsNone(await self.state.get_state())
                        self.assertEqual(await self.state.get_data(), {})
        self.delete.assert_not_awaited()
        self.store.assert_not_awaited()

    async def test_start_exits_active_upload(self):
        await self.active()
        self.assertEqual(await self.send("/start"), "cmd_start")
        self.assertIsNone(await self.state.get_state())
        self.assertEqual(await self.state.get_data(), {})

    async def test_multi_expenses_blocked_during_upload_and_work_after_navigation(self):
        self.use_real_handlers(expenses.add_transaction)
        await self.uploaded_files()
        family = SimpleNamespace(id=1, language="ru", currency="EUR")
        rows = [SimpleNamespace(title=title, amount=amount, type="expense", category="🛒 Продукты")
                for title, amount in (("хлеб", 2), ("молоко", 3))]
        with patch.object(expenses, "require_family_for_chat", AsyncMock(return_value=family)), \
             patch.object(expenses, "get_user_by_telegram_id", AsyncMock(return_value=SimpleNamespace(family_id=1))), \
             patch.object(expenses, "save_transaction_batch", AsyncMock(return_value=rows)) as batch, \
             patch.object(expenses, "save_transaction", AsyncMock()) as single:
            await self.send("хлеб 2 молоко 3")
            batch.assert_not_awaited()
            single.assert_not_awaited()
            self.answer.assert_awaited_once_with(t("ru", "documents.upload_prompt"))
            self.assertEqual(await self.state.get_state(), DocumentState.files.state)
            self.assertEqual(await self.send(t("ru", "menu.settings")), "open_settings")
            self.assertIsNone(await self.state.get_state())
            self.answer.reset_mock()
            await self.send("хлеб 2 молоко 3")
            batch.assert_awaited_once_with(["хлеб 2", "молоко 3"], 10, 1)
            single.assert_not_awaited()
            self.answer.assert_awaited_once()
            self.assertIn(t("ru", "quick.saved", count=2), self.answer.await_args.args[0])

    def use_real_handlers(self, *handlers):
        for clone in self.dp.sub_routers:
            for index, registered in enumerate(clone.message.handlers):
                for real in handlers:
                    if registered.callback is self.destinations[real.__name__]:
                        clone.message.handlers[index] = HandlerObject(callback=real, filters=registered.filters)

    async def assert_files_settings_and_parser(self, *, press_done, count=4):
        self.use_real_handlers(settings.open_settings, expenses.add_transaction)
        saved = await self.uploaded_files(count)
        saved_files = [dict(item) for item in saved.files]
        if press_done:
            await self.action("done")
            self.assertIsNone(await self.state.get_state())
        else:
            self.assertEqual(await self.state.get_state(), DocumentState.files.state)
            self.callback.answer.assert_not_awaited()
        self.answer.reset_mock()
        settings_data = dict(language="ru", currency="EUR", country="DE", city="Berlin",
                             timezone="Europe/Berlin", temporary_screen_ttl=20)
        with patch.object(settings, "_current_settings_or_error", AsyncMock(return_value=settings_data)):
            await self.send(t("ru", "menu.settings"))
        self.assertIn("Berlin", self.answer.await_args.args[0])
        self.answer.assert_awaited_once()
        self.assertIsNone(await self.state.get_state())
        self.assertEqual(await self.state.get_data(), {})
        family = SimpleNamespace(id=1, language="ru", currency="EUR")
        with patch.object(expenses, "require_family_for_chat", AsyncMock(return_value=family)), \
             patch.object(expenses, "get_user_by_telegram_id", AsyncMock(return_value=SimpleNamespace(family_id=1))), \
             patch.object(expenses, "parse_message", wraps=expenses.parse_message) as parse, \
             patch.object(expenses, "save_transaction", AsyncMock(return_value="PARSE_ERROR")) as save:
            await self.send("Кофе 3")
        parse.assert_called_once_with("Кофе 3")
        save.assert_awaited_once_with("Кофе 3", 10, 1)
        self.assertIsNone(await self.state.get_state())
        self.delete.assert_not_awaited()
        self.assertEqual(self.store.await_count, count)
        self.assertEqual(saved.id, 77)
        self.assertEqual(saved.files, saved_files)
        # The old panel cannot restart or delete the completed upload.
        for action in ("add_file", "done", "delete_draft_document"):
            await self.action(action)
            self.assertIsNone(await self.state.get_state())
        self.delete.assert_not_awaited()

    async def test_scenario_a_four_files_done_then_settings_and_coffee(self):
        await self.assert_files_settings_and_parser(press_done=True)

    async def test_scenario_b_four_files_settings_without_done_then_coffee(self):
        await self.assert_files_settings_and_parser(press_done=False)

    async def test_first_file_settings_without_done_then_coffee(self):
        await self.assert_files_settings_and_parser(press_done=False, count=1)

    async def assert_navigation_without_done(self, key, handler, screen_name):
        self.use_real_handlers(handler)
        saved = await self.uploaded_files()
        saved_files = [dict(item) for item in saved.files]
        with patch.object(menu, screen_name, AsyncMock()) as screen:
            await self.send(t("ru", f"menu.{key}"))
        screen.assert_awaited_once()
        self.assertIsNone(await self.state.get_state())
        self.assertEqual(await self.state.get_data(), {})
        self.assertEqual(saved.files, saved_files)
        self.delete.assert_not_awaited()
        self.callback.answer.assert_not_awaited()
        self.answer.assert_not_awaited()

    async def test_active_upload_month_without_done(self):
        await self.assert_navigation_without_done("month", menu.month_menu, "month")

    async def test_active_upload_analytics_without_done(self):
        await self.assert_navigation_without_done("analytics", menu.analytics_menu, "analytics")

    async def test_reproduce_navigation_trap_without_middleware(self):
        self.dp.message.outer_middleware.unregister(self.dp.message.outer_middleware[0])
        await self.uploaded_files()
        await self.send(t("ru", "menu.settings"))
        self.destinations["open_settings"].assert_not_awaited()
        self.assertEqual(await self.state.get_state(), DocumentState.files.state)
        await self.send("кофе 3")
        self.destinations["add_transaction"].assert_not_awaited()
        self.assertEqual(self.answer.await_count, 2)

    async def test_failed_panel_edit_replaces_panel_and_keeps_session(self):
        await self.active()
        await self.photo()
        message = SimpleNamespace(bot=SimpleNamespace(
            edit_message_text=AsyncMock(side_effect=TelegramBadRequest(
                method=EditMessageText(chat_id=10, message_id=500, text="Files"), message="message to edit not found")),
            edit_message_reply_markup=AsyncMock(side_effect=TelegramBadRequest(
                method=EditMessageText(chat_id=10, message_id=500, text="Files"), message="message to edit not found"))),
            answer=AsyncMock(return_value=SimpleNamespace(chat=SimpleNamespace(id=10), message_id=501)))
        await documents._update_upload_control(message, self.state, "ru", 1)
        self.assertEqual((await self.state.get_data())["upload_control_message_id"], 501)
        self.assertEqual(await self.state.get_state(), DocumentState.files.state)

    async def test_other_fsm_not_cleared(self):
        await self.state.set_state("Other:state")
        await self.send(t("ru", "menu.settings"))
        self.assertEqual(await self.state.get_state(), "Other:state")

    async def test_done_edit_failure_clears_before_ui_and_answers(self):
        await self.active()
        await self.photo()
        self.panel.edit_text.side_effect = TelegramBadRequest(
            method=EditMessageText(chat_id=10, message_id=500, text="Done"), message="message to edit not found")
        await self.action("done")
        self.assertIsNone(await self.state.get_state())
        self.panel.answer.assert_awaited_once()
        self.callback.answer.assert_awaited()

    async def test_stale_buttons_after_done_and_during_new_session(self):
        await self.active()
        await self.photo()
        await self.action("done")
        for action in ("add_file", "done", "delete_draft_document"):
            await self.action(action)
            self.assertIsNone(await self.state.get_state())
        await self.active()
        for action in ("add_file", "done", "delete_draft_document"):
            await self.action(action)
            self.assertEqual(await self.state.get_state(), DocumentState.files.state)
        await self.state.update_data(upload_control_chat_id=10, upload_control_message_id=501)
        for action in ("add_file", "done", "delete_draft_document"):
            await self.action(action)
            self.assertEqual((await self.state.get_data())["upload_control_message_id"], 501)
        self.delete.assert_not_awaited()

    async def test_stale_upload_callbacks_preserve_other_fsm(self):
        await self.state.set_state("Other:state")
        await self.state.set_data({"other_session": "keep"})
        for action in ("add_file", "done", "delete_draft_document"):
            await self.action(action)
            self.assertEqual(await self.state.get_state(), "Other:state")
            self.assertEqual(await self.state.get_data(), {"other_session": "keep"})
        self.delete.assert_not_awaited()

    async def test_missing_key_clears_even_for_text(self):
        await self.state.set_state(DocumentState.files)
        await self.send("кофе 3")
        self.assertIsNone(await self.state.get_state())
        self.answer.assert_awaited_once_with(t("ru", "documents.upload_expired"))
        self.destinations["add_transaction"].assert_not_awaited()

    async def test_deleted_document_and_unavailable_category_clear_session(self):
        await self.active()
        await self.state.update_data(document_id=77)
        self.get.return_value = None
        await self.photo()
        self.assertIsNone(await self.state.get_state())
        self.store.assert_not_awaited()
        await self.active()
        self.store.return_value = None
        await self.photo()
        self.assertIsNone(await self.state.get_state())

    async def test_duplicate_file_keeps_valid_upload(self):
        await self.active()
        self.store.return_value.file_added = False
        await self.photo()
        self.assertEqual(await self.state.get_state(), DocumentState.files.state)
        await self.action("done")
        self.assertIsNone(await self.state.get_state())
