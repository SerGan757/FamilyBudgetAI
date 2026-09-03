import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from sqlalchemy import CheckConstraint, UniqueConstraint

from app.database.models import Document, DocumentCategory, DocumentFile
from app.i18n import t
from app.i18n.documents import SYSTEM_CATEGORY_NAMES, category_display_name
from app.i18n.translations import SUPPORTED_LANGUAGES
from app.keyboards.documents import documents_keyboard
from app.services import document_service
from app.handlers import documents, settings
from app.keyboards.documents import DocumentCallback
from app.keyboards.settings_menu import FamilySettingsCallback, family_settings_keyboard_for_ttl


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
