import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from sqlalchemy import CheckConstraint, UniqueConstraint
from aiogram.exceptions import TelegramBadRequest

from app.database.models import Document, DocumentCategory, DocumentFile
from app.i18n import t
from app.i18n.documents import SYSTEM_CATEGORY_NAMES, category_display_name
from app.i18n.translations import SUPPORTED_LANGUAGES
from app.keyboards.documents import documents_keyboard
from app.services import document_service
from app.handlers import documents, settings
from app.handlers.document_states import DocumentState
from app.keyboards.documents import DocumentCallback
from app.keyboards.settings_menu import FamilySettingsCallback, family_settings_keyboard_for_ttl
from app.constants import DOCUMENT_PREVIEW_TTL
from app.utils import temporary_screens


class MemoryState:
    def __init__(self, data=None, current=None):
        self.data = dict(data or {})
        self.current = current

    async def get_data(self): return dict(self.data)
    async def update_data(self, **values): self.data.update(values)
    async def get_state(self): return self.current
    async def set_state(self, value): self.current = getattr(value, "state", value)
    async def clear(self): self.data.clear(); self.current = None


class DocumentModelsTests(unittest.TestCase):
    def test_category_schema_and_family_uniqueness(self):
        columns = DocumentCategory.__table__.columns
        self.assertEqual(set(columns.keys()), {"id","family_id","code","name","emoji","sort_order","is_system","is_active","created_at"})
        self.assertFalse(columns.family_id.nullable)
        self.assertTrue(columns.name.nullable)
        uniques = [tuple(c.name for c in x.columns) for x in DocumentCategory.__table__.constraints if isinstance(x, UniqueConstraint)]
        self.assertIn(("family_id", "name"), uniques)

    def test_document_schema_and_access_constraint(self):
        columns = Document.__table__.columns
        self.assertEqual(set(columns.keys()), {"id","family_id","category_id","title","owner_name","note","expires_at","access_level","created_by_user_id","created_at","updated_at"})
        checks = " ".join(str(x.sqltext) for x in Document.__table__.constraints if isinstance(x, CheckConstraint))
        self.assertIn("private", checks)
        self.assertEqual(next(iter(Document.__table__.c.category_id.foreign_keys)).ondelete, "RESTRICT")

    def test_file_schema_and_cascade(self):
        self.assertIn("telegram_file_id", DocumentFile.__table__.columns)
        self.assertEqual(next(iter(DocumentFile.__table__.c.document_id.foreign_keys)).ondelete, "CASCADE")

    def test_controlled_migration_documents_rules(self):
        source = open("docs/migrations/20260903_add_documents.sql", encoding="utf-8").read().lower()
        for table in ("document_categories", "documents", "document_files"):
            self.assertIn(f"create table {table}", source)
        self.assertIn("on delete restrict", source)
        self.assertIn("on delete cascade", source)


class DocumentUiTests(unittest.TestCase):
    def test_i18n_keys_exist_for_all_locales(self):
        keys = ("menu.documents","documents.title","documents.add_document","documents.search","documents.private_denied")
        for language in SUPPORTED_LANGUAGES:
            for key in keys:
                self.assertNotEqual(t(language, key), key)

    def test_compact_category_grid(self):
        categories = [SimpleNamespace(id=i, emoji="📁", name=f"C{i}") for i in range(1, 4)]
        keyboard = documents_keyboard(categories, "en")
        self.assertEqual([len(row) for row in keyboard.inline_keyboard[:2]], [2, 1])
        payload = " ".join(button.callback_data or "" for row in keyboard.inline_keyboard for button in row)
        self.assertNotIn("family_id", payload)

    def test_system_categories_are_translated_in_all_locales(self):
        category = SimpleNamespace(code="car", name=None)
        for language in SUPPORTED_LANGUAGES:
            self.assertEqual(category_display_name(language, category), SYSTEM_CATEGORY_NAMES[language]["car"])

    def test_custom_system_name_has_priority(self):
        category = SimpleNamespace(code="car", name="Моя машина")
        self.assertEqual(category_display_name("ru", category), "Моя машина")

    def test_russian_system_category_buttons(self):
        categories = [SimpleNamespace(id=i, emoji=emoji, code=code, name=None) for i,(code,emoji) in enumerate(document_service.DEFAULT_CATEGORIES,1)]
        texts = [button.text for row in documents_keyboard(categories,"ru").inline_keyboard for button in row]
        for expected in ("👤 Личные документы","👨‍👩‍👧‍👦 Семья","🚗 Автомобиль","🏠 Жильё","🇩🇪 Германия / ведомства","🩺 Медицина","💼 Работа","✈️ Поездки","📁 Прочее"):
            self.assertIn(expected, texts)

    def test_settings_entry_and_documents_root_back_callbacks(self):
        settings_keyboard = family_settings_keyboard_for_ttl(20, "ru")
        settings_button = next(button for row in settings_keyboard.inline_keyboard for button in row if button.text == "📂 Документы")
        self.assertEqual(FamilySettingsCallback.unpack(settings_button.callback_data).action, "documents")
        root = documents_keyboard([], "ru")
        self.assertEqual(DocumentCallback.unpack(root.inline_keyboard[-1][0].callback_data).action, "settings")

    def test_documents_handler_remains_registered(self):
        from app.handlers import routers
        names = [getattr(item.callback, "__name__", "") for router in routers for item in router.message.handlers]
        self.assertIn("documents_menu", names)


class DocumentNavigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_settings_callback_opens_documents_root(self):
        message = AsyncMock()
        callback = SimpleNamespace(message=message, from_user=SimpleNamespace(id=10), answer=AsyncMock())
        state = AsyncMock()
        current = {"language":"ru", "temporary_screen_ttl":20}
        with patch.object(settings, "get_current_family_settings", AsyncMock(return_value=current)), patch.object(documents, "show_documents", AsyncMock()) as show:
            await settings.family_settings_callback(callback, SimpleNamespace(action="documents", value=""), state)
        show.assert_awaited_once_with(message, 10)


class DocumentPreviewTests(unittest.IsolatedAsyncioTestCase):
    def _callback(self, photo_messages=None, document_messages=None):
        message = SimpleNamespace(
            answer_photo=AsyncMock(side_effect=photo_messages or []),
            answer_document=AsyncMock(side_effect=document_messages or []),
        )
        return SimpleNamespace(
            message=message, from_user=SimpleNamespace(id=10), answer=AsyncMock(),
        )

    async def _get(self, callback, document):
        state = MemoryState()
        with patch.object(documents, "_lang", AsyncMock(return_value="ru")), \
             patch.object(documents, "get_document", AsyncMock(return_value=document)), \
             patch.object(documents, "schedule_temporary_message") as schedule:
            await documents.document_callback(
                callback, SimpleNamespace(action="get", value=document.id), state,
            )
        return schedule

    async def test_one_preview_schedules_one_delete_with_documents_ttl(self):
        preview = SimpleNamespace(message_id=101)
        document = SimpleNamespace(
            id=7, files=[SimpleNamespace(file_type="photo", telegram_file_id="file-id")],
        )
        callback = self._callback(photo_messages=[preview])
        schedule = await self._get(callback, document)
        schedule.assert_called_once_with(preview, ttl=DOCUMENT_PREVIEW_TTL)
        self.assertEqual(DOCUMENT_PREVIEW_TTL, 180)

    async def test_two_previews_schedule_their_returned_messages(self):
        first = SimpleNamespace(message_id=101)
        second = SimpleNamespace(message_id=102)
        files = [
            SimpleNamespace(file_type="photo", telegram_file_id="photo-id"),
            SimpleNamespace(file_type="document", telegram_file_id="document-id"),
        ]
        document = SimpleNamespace(id=7, files=files)
        callback = self._callback(photo_messages=[first], document_messages=[second])
        schedule = await self._get(callback, document)
        self.assertEqual(
            schedule.call_args_list,
            [unittest.mock.call(first, ttl=180), unittest.mock.call(second, ttl=180)],
        )
        self.assertEqual(document.files, files)
        self.assertEqual(files[0].telegram_file_id, "photo-id")
        self.assertEqual(files[1].telegram_file_id, "document-id")

    async def test_repeated_get_sends_and_schedules_files_again(self):
        previews = [SimpleNamespace(message_id=101), SimpleNamespace(message_id=102)]
        document = SimpleNamespace(
            id=7, access_level="private",
            files=[SimpleNamespace(file_type="photo", telegram_file_id="file-id")],
        )
        callback = self._callback(photo_messages=previews)
        state = MemoryState()
        with patch.object(documents, "_lang", AsyncMock(return_value="ru")), \
             patch.object(documents, "get_document", AsyncMock(return_value=document)) as get, \
             patch.object(documents, "schedule_temporary_message") as schedule:
            for _ in range(2):
                await documents.document_callback(
                    callback, SimpleNamespace(action="get", value=7), state,
                )
        self.assertEqual(get.await_count, 2)
        self.assertEqual(callback.message.answer_photo.await_count, 2)
        self.assertEqual(schedule.call_count, 2)

    async def test_family_document_uses_the_same_temporary_preview_path(self):
        preview = SimpleNamespace(message_id=201)
        document = SimpleNamespace(
            id=8, access_level="family",
            files=[SimpleNamespace(file_type="document", telegram_file_id="family-file")],
        )
        callback = self._callback(document_messages=[preview])
        schedule = await self._get(callback, document)
        schedule.assert_called_once_with(preview, ttl=180)

    async def test_delete_error_is_best_effort(self):
        bot = SimpleNamespace(
            delete_message=AsyncMock(
                side_effect=TelegramBadRequest(method=Mock(), message="message not found"),
            ),
        )
        with patch.object(temporary_screens.asyncio, "sleep", AsyncMock()):
            await temporary_screens._delete_after(bot, 100, 101, 180)
        bot.delete_message.assert_awaited_once_with(chat_id=100, message_id=101)


class DocumentUploadPanelTests(unittest.IsolatedAsyncioTestCase):
    def _incoming_photo(self, bot, file_id, control=None):
        photo = SimpleNamespace(file_id=file_id, file_unique_id=f"unique-{file_id}")
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=10), photo=[photo], document=None,
            bot=bot, answer=AsyncMock(return_value=control),
        )
        return message

    async def test_first_file_creates_panel_and_second_edits_same_panel(self):
        bot = SimpleNamespace(edit_message_text=AsyncMock(), edit_message_reply_markup=AsyncMock())
        control = SimpleNamespace(chat=SimpleNamespace(id=100), message_id=500)
        state = MemoryState({"files": []}, DocumentState.files.state)
        first = self._incoming_photo(bot, "file-1", control)
        with patch.object(documents, "_lang", AsyncMock(return_value="ru")):
            await documents.receive_file(first, state)
        self.assertEqual(len(state.data["files"]), 1)
        self.assertEqual(state.data["upload_control_message_id"], 500)
        first.answer.assert_awaited_once()

        panel_message = SimpleNamespace(
            chat=SimpleNamespace(id=100), message_id=500,
            edit_text=AsyncMock(),
        )
        add_callback = SimpleNamespace(
            message=panel_message, from_user=SimpleNamespace(id=10), answer=AsyncMock(),
        )
        with patch.object(documents, "_lang", AsyncMock(return_value="ru")):
            await documents.document_callback(
                add_callback, SimpleNamespace(action="add_file", value=0), state,
            )

        second = self._incoming_photo(bot, "file-2")
        with patch.object(documents, "_lang", AsyncMock(return_value="ru")):
            await documents.receive_file(second, state)
        self.assertEqual(len(state.data["files"]), 2)
        second.answer.assert_not_awaited()
        bot.edit_message_text.assert_awaited_once()
        self.assertIn("Файлов: 2", bot.edit_message_text.await_args.kwargs["text"])

    async def test_save_once_deactivates_panel_and_stale_save_is_answered(self):
        files = [{"telegram_file_id":"one"}, {"telegram_file_id":"two"}]
        state = MemoryState(
            {"category_id":7,"title":"Passport","owner":"Me","access_level":"private","files":files,
             "upload_control_chat_id":100,"upload_control_message_id":500},
            DocumentState.files.state,
        )
        message = SimpleNamespace(chat=SimpleNamespace(id=100), message_id=500, edit_text=AsyncMock(), answer=AsyncMock())
        callback = SimpleNamespace(message=message, from_user=SimpleNamespace(id=10), answer=AsyncMock())
        created = SimpleNamespace(category_id=7)
        with patch.object(documents, "_lang", AsyncMock(return_value="ru")), \
             patch.object(documents, "create_document", AsyncMock(return_value=created)) as create, \
             patch.object(documents, "get_category", AsyncMock(return_value=None)), \
             patch.object(documents, "list_documents", AsyncMock(return_value=[])):
            await documents.document_callback(callback, SimpleNamespace(action="save", value=0), state)
            stale = SimpleNamespace(message=message, from_user=SimpleNamespace(id=10), answer=AsyncMock())
            await documents.document_callback(stale, SimpleNamespace(action="save", value=0), state)
        create.assert_awaited_once()
        self.assertEqual(len(create.await_args.args[-1]), 2)
        self.assertIsNone(state.current)
        self.assertEqual(state.data, {})
        self.assertIsNone(message.edit_text.await_args.kwargs["reply_markup"])
        stale.answer.assert_awaited_once_with("Эта операция уже завершена.", show_alert=False)

    async def test_cancel_clears_state_and_removes_old_controls(self):
        state = MemoryState({"files":[{"telegram_file_id":"one"}]}, DocumentState.files.state)
        message = SimpleNamespace(chat=SimpleNamespace(id=100), message_id=500, edit_reply_markup=AsyncMock())
        callback = SimpleNamespace(message=message, from_user=SimpleNamespace(id=10), answer=AsyncMock())
        with patch.object(documents, "_lang", AsyncMock(return_value="ru")), \
             patch.object(documents, "show_documents", AsyncMock()):
            await documents.document_callback(callback, SimpleNamespace(action="cancel", value=0), state)
        self.assertEqual(state.data, {})
        self.assertIsNone(state.current)
        message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)

    async def test_replaced_old_panel_is_stale_while_fsm_is_active(self):
        state = MemoryState(
            {"files":[{"telegram_file_id":"one"}], "upload_control_chat_id":100,
             "upload_control_message_id":501},
            DocumentState.files.state,
        )
        old_message = SimpleNamespace(chat=SimpleNamespace(id=100), message_id=500)
        callback = SimpleNamespace(message=old_message, from_user=SimpleNamespace(id=10), answer=AsyncMock())
        with patch.object(documents, "_lang", AsyncMock(return_value="ru")), \
             patch.object(documents, "create_document", AsyncMock()) as create:
            await documents.document_callback(callback, SimpleNamespace(action="save", value=0), state)
        create.assert_not_awaited()
        callback.answer.assert_awaited_once_with("Эта операция уже завершена.", show_alert=False)

    async def test_documents_root_back_returns_to_settings(self):
        message = AsyncMock()
        callback = SimpleNamespace(message=message, from_user=SimpleNamespace(id=10), answer=AsyncMock())
        state = AsyncMock()
        with patch.object(documents, "get_current_family_settings", AsyncMock(return_value={"language":"ru"})), patch.object(settings, "_show_current_settings", AsyncMock()) as show:
            await documents.document_callback(callback, SimpleNamespace(action="settings", value=0), state)
        show.assert_awaited_once_with(message, 10)


class DocumentServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_categories_are_idempotent(self):
        user = SimpleNamespace(id=1, family_id=7)
        names_result = SimpleNamespace(scalars=lambda: [])
        max_result = SimpleNamespace(scalar_one=lambda: -1)
        session = AsyncMock()
        session.add = Mock()
        session.execute.side_effect = [AsyncMock(scalar_one_or_none=lambda: user), names_result, max_result]
        manager = AsyncMock(); manager.__aenter__.return_value = session
        with patch.object(document_service, "SessionLocal", return_value=manager), patch.object(document_service, "list_categories", AsyncMock(return_value=[])):
            await document_service.ensure_default_categories(10)
        self.assertEqual(session.add.call_count, len(document_service.DEFAULT_CATEGORIES))
        session.commit.assert_awaited_once()

    async def test_search_query_is_scoped_to_family_and_private_owner(self):
        # Query structure is the security boundary; execution is mocked here.
        user = SimpleNamespace(id=11, family_id=7)
        user_result = SimpleNamespace(scalar_one_or_none=lambda: user)
        documents_result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
        session = AsyncMock(); session.execute.side_effect = [user_result, documents_result]
        manager = AsyncMock(); manager.__aenter__.return_value = session
        with patch.object(document_service, "SessionLocal", return_value=manager):
            self.assertEqual(await document_service.search_documents(10, "passport"), [])
        sql = str(session.execute.await_args_list[1].args[0])
        self.assertIn("documents.family_id", sql)
        self.assertIn("documents.created_by_user_id", sql)

    async def test_get_document_respects_private_access(self):
        user = SimpleNamespace(id=11, family_id=7)
        session = AsyncMock()
        session.execute.side_effect = [SimpleNamespace(scalar_one_or_none=lambda: user), SimpleNamespace(scalar_one_or_none=lambda: None)]
        manager = AsyncMock(); manager.__aenter__.return_value = session
        with patch.object(document_service, "SessionLocal", return_value=manager):
            self.assertIsNone(await document_service.get_document(10, 99))
        sql = str(session.execute.await_args_list[1].args[0])
        self.assertIn("documents.access_level", sql)
