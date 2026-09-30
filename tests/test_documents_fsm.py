import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiogram import Bot, Dispatcher, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.dispatcher.event.handler import HandlerObject
from aiogram.methods import EditMessageText
from aiogram.types import Chat, Message, Update, User
from sqlalchemy import MetaData, create_engine, select
from sqlalchemy.orm import Session

from app.handlers import documents, expenses, menu, routers, settings
from app.handlers.document_navigation import DocumentNavigationMiddleware
from app.handlers.document_states import DocumentState
from app.i18n import t
from app.i18n.translations import SUPPORTED_LANGUAGES
from app.keyboards.documents import DocumentCallback
from app.keyboards.main_menu import main_menu_keyboard
from app.database.db import Base
from app.database.models import DocumentFile, Family, FamilyCategory, Project, Transaction
from app.services import document_service, expense_service
from app.services.category_service import detect_category
from app.services.parser import is_financial_handoff, parse_message
from test_multi_expense_input import SQLiteSession


class FinancialSession(SQLiteSession):
    def add(self, row):
        self.session.add(row)

    async def commit(self):
        self.session.commit()

    async def refresh(self, row):
        self.session.refresh(row)


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
        self.stack.enter_context(patch.object(self.bot, "edit_message_text", AsyncMock()))
        self.received_expenses = []

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
                          from_user=User(id=10, is_bot=False, first_name="Test"), text=text).as_(self.bot)
        self.last_message = message
        return await self.dp.feed_update(self.bot, Update(update_id=1, message=message).as_(self.bot))

    async def photo(self, file_id="file", *, routed=False):
        if routed:
            message = Message(message_id=2, date=datetime.now(timezone.utc), chat=Chat(id=10, type="private"),
                              from_user=User(id=10, is_bot=False, first_name="Test"),
                              photo=[dict(file_id=file_id, file_unique_id=f"unique-{file_id}",
                                          width=100, height=100)]).as_(self.bot)
            await self.dp.feed_update(self.bot, Update(update_id=2, message=message).as_(self.bot))
            return message
        message = SimpleNamespace(from_user=SimpleNamespace(id=10), text=None, document=None,
            photo=[SimpleNamespace(file_id=file_id, file_unique_id=f"unique-{file_id}")],
            answer=AsyncMock(return_value=self.panel), bot=SimpleNamespace(edit_message_text=AsyncMock()))
        await documents.receive_file(message, self.state)
        return message

    async def uploaded_files(self, count=4, *, routed=False):
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
            message = await self.photo(f"file-{index}", routed=routed)
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

    async def send_document(self, filename, mime, file_id="document"):
        message = Message(message_id=3, date=datetime.now(timezone.utc), chat=Chat(id=10, type="private"),
                          from_user=User(id=10, is_bot=False, first_name="Test"),
                          document=dict(file_id=file_id, file_unique_id=f"unique-{file_id}",
                                        file_name=filename, mime_type=mime, file_size=1_100_000)).as_(self.bot)
        await self.dp.feed_update(self.bot, Update(update_id=3, message=message).as_(self.bot))

    async def test_telegram_document_allowlist_reaches_storage(self):
        await self.active()
        for mime, extensions in document_service.DOCUMENT_EXTENSIONS_BY_MIME.items():
            for extension in extensions:
                self.store.reset_mock()
                await self.send_document("file" + extension, mime)
                self.store.assert_awaited_once()
                self.assertEqual(self.store.await_args.args[-1]["mime_type"], mime)
        for name, mime in (("file.exe", "application/msword"), ("file.docx", "application/octet-stream"),
                           ("file.zip", "application/zip"), ("file.pdf", None),
                           ("file.bat", "text/plain"), ("file.ps1", "text/plain"), ("file.unknown", "image/png")):
            self.store.reset_mock()
            await self.send_document(name, mime)
            self.store.assert_not_awaited()
            self.assertEqual(self.answer.await_args.args[0], t("ru", "documents.invalid_file"))

    async def test_docx_pdf_real_service_flow_duplicate_and_financial_handoff(self):
        self.real_financial_services()
        await self.action("new_document")
        await self.send("Nikita Ausweis A4")
        await self.action("owner_me")
        await self.action("access_private")
        data = await self.state.get_data()
        stored = SimpleNamespace(id=77, family_id=1, created_by_user_id=1, category_id=7,
                                 title=data["title"], owner_name=data["owner"], access_level=data["access_level"], files=[])
        self.get.return_value = stored
        session = AsyncMock()
        session.add = Mock(side_effect=stored.files.append)
        manager = AsyncMock()
        manager.__aenter__.return_value = session
        self.stack.enter_context(patch.object(document_service, "SessionLocal", return_value=manager))
        self.stack.enter_context(patch.object(document_service, "get_document", AsyncMock(return_value=stored)))
        self.store.side_effect = document_service.create_or_append_document_file

        def prepare(existing=None):
            def result(value):
                return SimpleNamespace(scalar_one_or_none=lambda: value, scalar_one=lambda: value)
            count = len(stored.files)
            session.execute.side_effect = [result(SimpleNamespace(id=1, family_id=1)),
                result(SimpleNamespace(id=7)), result(None), result(stored), result(existing)] + (
                [result(count)] if existing else [result(count - 1), result(count + 1)])

        docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        # Desktop drop/attachment and Android attachment share this Bot API
        # Document representation; the server has no client-specific branch.
        self.answer.reset_mock()
        prepare()
        await self.send_document("nikita_Ausweis.docx", docx, "word")
        self.assertEqual(len(stored.files), 1)
        self.assertIsInstance(stored.files[0], DocumentFile)
        self.assertEqual((stored.files[0].original_filename, stored.files[0].mime_type,
                          stored.files[0].telegram_file_id, stored.files[0].telegram_file_unique_id),
                         ("nikita_Ausweis.docx", docx, "word", "unique-word"))
        self.assertEqual((await self.state.get_data())["file_count"], 1)
        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        self.assertEqual(await self.state.get_state(), DocumentState.files.state)
        self.answer.assert_awaited_once()
        panel = self.answer.await_args
        self.assertIn(t("ru", "documents.files", count=1), panel.args[0])
        self.assertEqual(
            [DocumentCallback.unpack(button.callback_data).action
             for row in panel.kwargs["reply_markup"].inline_keyboard for button in row],
            ["add_file", "done", "delete_draft_document"],
        )
        prepare(stored.files[0])
        await self.send_document("nikita_Ausweis.docx", docx, "word")
        self.assertEqual(len(stored.files), 1)
        self.assertEqual((await self.state.get_data())["file_count"], 1)
        await self.action("add_file")
        prepare()
        await self.send_document("second.pdf", "application/pdf", "pdf")
        self.assertEqual((await self.state.get_data())["file_count"], 2)
        self.assertEqual(await self.state.get_state(), DocumentState.files.state)
        self.assertEqual(session.add.call_count, 2)
        self.assertEqual(session.commit.await_count, 3)
        self.assertFalse(any(call.args[0] == t("ru", "documents.invalid_file") for call in self.answer.await_args_list))
        await self.send("Заказ +50 #заказ")
        self.assertIs(self.received_expenses[-1], self.last_message)
        self.assertEqual(self.stored_transactions()[0].project_id, 43)
        self.assertIsNone(await self.state.get_state())
        self.assertEqual(len(stored.files), 2)
        self.delete.assert_not_awaited()

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

    async def test_invalid_text_after_saved_files_stays_in_upload(self):
        saved = await self.uploaded_files()
        saved_files = [dict(item) for item in saved.files]
        await self.send("hello")
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

    async def test_multi_expenses_blocked_before_files_and_forwarded_after_save(self):
        self.use_real_handlers(expenses.add_transaction)
        await self.active()
        family = SimpleNamespace(id=1, language="ru", currency="EUR")
        rows = [SimpleNamespace(id=index, family_id=1, user_id=1,
                                created_at=datetime(2026, 9, 29),
                                title=title, amount=amount, type="expense", category="🛒 Продукты")
                for index, (title, amount) in enumerate((("хлеб", 2), ("молоко", 3)), 1)]
        with patch.object(expenses, "require_family_for_chat", AsyncMock(return_value=family)), \
             patch.object(expenses, "get_user_by_telegram_id", AsyncMock(return_value=SimpleNamespace(family_id=1))), \
             patch.object(expenses, "save_transaction_batch", AsyncMock(return_value=rows)) as batch, \
             patch.object(expenses, "save_transaction", AsyncMock()) as single:
            await self.send("хлеб 2 молоко 3")
            batch.assert_not_awaited()
            single.assert_not_awaited()
            self.answer.assert_awaited_once_with(t("ru", "documents.upload_prompt"))
            self.assertEqual(await self.state.get_state(), DocumentState.files.state)
            saved = await self.uploaded_files()
            self.answer.reset_mock()
            await self.send("хлеб 2 молоко 3")
            batch.assert_awaited_once_with(["хлеб 2", "молоко 3"], 10, 1)
            single.assert_not_awaited()
            self.answer.assert_awaited_once()
            self.assertIn(t("ru", "quick.saved", count=2), self.answer.await_args.args[0])
            self.assertIsNone(await self.state.get_state())
            self.assertEqual(len(saved.files), 4)
            self.delete.assert_not_awaited()

    def use_real_handlers(self, *handlers):
        for clone in self.dp.sub_routers:
            for index, registered in enumerate(clone.message.handlers):
                for real in handlers:
                    if registered.callback is self.destinations[real.__name__]:
                        clone.message.handlers[index] = HandlerObject(callback=real, filters=registered.filters)
                        if real is expenses.add_transaction:
                            async def capture(handler, event, data):
                                self.received_expenses.append(event)
                                return await handler(event, data)
                            clone.message.middleware(capture)

    def real_financial_services(self):
        """Keep real parser/save services; use an isolated SQLite transaction store."""
        self.use_real_handlers(expenses.add_transaction)
        self.engine = create_engine("sqlite:///:memory:")
        self.stack.callback(self.engine.dispose)
        metadata = MetaData()
        for table in Base.metadata.tables.values():
            table.to_metadata(metadata)
        tables = [metadata.tables[model.__tablename__] for model in (Family, FamilyCategory, Project, Transaction)]
        for table in tables:
            for column in table.columns:
                if column.server_default is not None and "AT TIME ZONE" in str(column.server_default.arg):
                    column.server_default = None
        metadata.create_all(self.engine, tables=tables)
        with Session(self.engine) as session:
            session.add(Family(id=1, name="Test", invite_code="routing-test"))
            session.add(Project(id=42, family_id=1, name="Ремонт", tag="ремонт"))
            session.add(Project(id=43, family_id=1, name="Заказ", tag="заказ"))
            session.commit()
        family = SimpleNamespace(id=1, language="ru", currency="EUR")
        user = SimpleNamespace(id=1, family_id=1)
        self.stack.enter_context(patch.object(expenses, "require_family_for_chat", AsyncMock(return_value=family)))
        for module in (expenses, expense_service):
            self.stack.enter_context(patch.object(module, "get_user_by_telegram_id", AsyncMock(return_value=user)))
        self.stack.enter_context(patch.object(expense_service, "SessionLocal",
                                            side_effect=lambda: FinancialSession(self.engine, [])))
        self.stack.enter_context(patch.object(expense_service, "detect_category_reference_for_family",
                                            AsyncMock(side_effect=lambda family, title, kind: (*detect_category(title, kind), None))))
        self.stack.enter_context(patch.object(expense_service, "find_family_project_by_tag",
                                            AsyncMock(side_effect=lambda family, tag: SimpleNamespace(
                                                id=43 if tag == "заказ" else 42,
                                                name="Заказ" if tag == "заказ" else "Ремонт", is_active=True))))

    async def test_saved_upload_then_order_income_project_unchanged(self):
        self.real_financial_services()
        saved = await self.uploaded_files(2, routed=True)
        files = list(saved.files)
        text = "Заказ +50 #заказ"
        with patch.object(expenses, "save_transaction", wraps=expense_service.save_transaction) as save:
            await self.send(text)
        save.assert_awaited_once_with(text, 10, 1)
        self.assertIs(self.received_expenses[-1], self.last_message)
        self.assertEqual(self.last_message.text, text)
        row, = self.stored_transactions()
        self.assertEqual((row.title, row.amount, row.type, row.project_id), ("Заказ", 50, "income", 43))
        icon, category = detect_category("Заказ", "income")
        self.assertEqual(row.category, f"{icon} {category}")
        confirmation = self.answer.await_args
        self.assertIn("Заказ", confirmation.args[0])
        self.assertEqual(confirmation.kwargs["reply_markup"].inline_keyboard[0][0].callback_data,
                         f"undo_op:transaction:{row.id}")
        self.assertIsNone(await self.state.get_state())
        self.assertEqual(saved.files, files)
        self.delete.assert_not_awaited()

    def stored_transactions(self):
        with Session(self.engine) as session:
            return list(session.scalars(select(Transaction).order_by(Transaction.id)))

    async def test_two_uploaded_files_then_fuel_reaches_real_expenses_with_same_message(self):
        self.real_financial_services()
        saved = await self.uploaded_files(2, routed=True)
        files = [dict(item) for item in saved.files]
        with patch.object(expenses, "parse_message", wraps=expenses.parse_message) as parser:
            await self.send("Бензин 25")
        parser.assert_called_once_with("Бензин 25")
        self.assertIs(self.received_expenses[-1], self.last_message)
        self.assertEqual([(row.title, row.amount, row.type) for row in self.stored_transactions()],
                         [("Бензин", 25, "expense")])
        self.assertIsNone(await self.state.get_state())
        self.assertEqual(await self.state.get_data(), {})
        self.assertEqual(saved.files, files)
        self.assertEqual(self.store.await_count, 2)
        self.delete.assert_not_awaited()
        # Old upload buttons cannot mutate the document after handoff.
        for action in ("done", "add_file", "delete_draft_document"):
            await self.action(action)
        self.delete.assert_not_awaited()

    async def test_four_uploaded_files_then_coffee_without_done(self):
        self.real_financial_services()
        saved = await self.uploaded_files(4, routed=True)
        await self.send("кофе 3")
        self.assertEqual([(row.title, row.amount) for row in self.stored_transactions()], [("кофе", 3)])
        self.assertIsNone(await self.state.get_state())
        self.assertEqual(len(saved.files), 4)
        self.delete.assert_not_awaited()

    async def test_uploaded_files_then_multi_expense_uses_atomic_batch_path(self):
        self.real_financial_services()
        saved = await self.uploaded_files(2, routed=True)
        with patch.object(expenses, "save_transaction_batch", wraps=expense_service.save_transaction_batch) as batch:
            await self.send("Бензин 9 продукты 60")
        batch.assert_awaited_once_with(["Бензин 9", "продукты 60"], 10, 1)
        self.assertEqual([(row.title, row.amount) for row in self.stored_transactions()],
                         [("Бензин", 9), ("продукты", 60)])
        self.assertIs(self.received_expenses[-1], self.last_message)
        self.assertIsNone(await self.state.get_state())
        self.assertEqual(len(saved.files), 2)
        self.delete.assert_not_awaited()

    async def test_invalid_financial_text_keeps_saved_upload_and_creates_nothing(self):
        self.real_financial_services()
        saved = await self.uploaded_files(2, routed=True)
        for text in ("hello", "кофе", "123 abc xyz", "кофе 3 хлеб x", "Бензин 25\nhello"):
            with self.subTest(text=text):
                self.answer.reset_mock()
                await self.send(text)
                self.assertEqual(self.stored_transactions(), [])
                self.assertEqual(self.received_expenses, [])
                self.assertEqual(await self.state.get_state(), DocumentState.files.state)
                self.answer.assert_awaited_once_with(t("ru", "documents.upload_prompt"))
        self.assertEqual(len(saved.files), 2)
        self.delete.assert_not_awaited()

    async def test_no_saved_file_does_not_forward_valid_financial_input(self):
        self.real_financial_services()
        await self.action("new_document")
        await self.send("Passport")
        await self.action("owner_me")
        await self.action("access_private")
        self.answer.reset_mock()
        for text in ("Бензин 25", "Бензин 9 продукты 60", "++500"):
            await self.send(text)
            self.assertEqual(await self.state.get_state(), DocumentState.files.state)
        self.assertEqual(self.stored_transactions(), [])
        self.assertEqual(self.received_expenses, [])

    async def test_existing_financial_formats_after_saved_upload(self):
        self.real_financial_services()
        for text, amount, kind in (("кофе 3.50", 3.5, "expense"), ("7.22 пицца", 7.22, "expense"),
                                   ("зарплата +2300", 2300, "income"), ("+150 возврат", 150, "income"),
                                   ("краска 45 #ремонт", 45, "expense")):
            with self.subTest(text=text):
                saved = await self.uploaded_files(1, routed=True)
                previous = len(self.stored_transactions())
                await self.send(text)
                rows = self.stored_transactions()
                self.assertEqual(len(rows), previous + 1)
                self.assertEqual((rows[-1].amount, rows[-1].type), (amount, kind))
                self.assertEqual(rows[-1].project_id, 42 if "#" in text else None)
                self.assertIsNone(await self.state.get_state())
                self.assertEqual(len(saved.files), 1)
        await self.uploaded_files(1, routed=True)
        previous = len(self.stored_transactions())
        with patch.object(expenses, "add_contribution", AsyncMock(return_value=None)) as goal:
            await self.send("++500")
        goal.assert_awaited_once_with(1, 10, 500)
        self.assertEqual(len(self.stored_transactions()), previous)
        self.assertIsNone(await self.state.get_state())

    def test_handoff_is_stricter_than_general_parser_without_changing_it(self):
        self.assertIsNotNone(parse_message("123 abc xyz"))
        self.assertFalse(is_financial_handoff("123 abc xyz"))
        for text in ("Бензин 25", "7.22 пицца", "++500", "краска 45 #ремонт", "Бензин 9 продукты 60"):
            self.assertTrue(is_financial_handoff(text), text)
        for text in ("hello", "кофе", "хлеб 2 молоко 3 #ремонт", "++500\nхлеб 2 молоко 3"):
            self.assertFalse(is_financial_handoff(text), text)

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
