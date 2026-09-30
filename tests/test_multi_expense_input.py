import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from contextlib import ExitStack, asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import MetaData, create_engine, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.dialects import postgresql
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText
from aiogram.types import CallbackQuery, Chat, InaccessibleMessage, User as TelegramUser

from app.database.db import Base
from app.database.models import Family, FamilyCategory, Transaction
from app.data.categories import CATEGORIES
from app.handlers import expenses
from app.i18n import t
from app.i18n.translations import SUPPORTED_LANGUAGES
from app.keyboards.undo import UndoBatchCallback, UndoOperationCallback, undo_batch_keyboard
from app.services import category_override_service, custom_category_service, expense_service, bulk_undo_service
from app.services.parser import parse_message, split_multi_expenses


class SQLiteSession:
    """Async-shaped adapter over real in-memory SQLAlchemy transactions.

    No async SQLite driver or external DB is required. PostgreSQL locking is
    not tested here; inserts, activity updates, commit and rollback are real.
    """
    def __init__(self, engine, saved):
        self.session = Session(engine, expire_on_commit=False)
        self.saved = saved
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.session.close()

    @asynccontextmanager
    async def begin(self):
        with self.session.begin():
            yield
        self.saved.extend(self.added)

    def add_all(self, items):
        self.added.extend(items)
        self.session.add_all(items)

    async def scalar(self, statement):
        return self.session.scalar(statement)

    async def execute(self, statement):
        return self.session.execute(statement)

    async def flush(self):
        self.session.flush()

    async def delete(self, row):
        self.session.delete(row)


class MultiExpenseParserTests(unittest.TestCase):
    def test_complete_pairs(self):
        for text, expected in (
            ("бензин 9 продукты 60", ["бензин 9", "продукты 60"]),
            ("кофе 3 булочка 2.50", ["кофе 3", "булочка 2.50"]),
            ("хлеб 2 молоко 1,50 сыр 4", ["хлеб 2", "молоко 1,50", "сыр 4"]),
            ("  свежий хлеб 2   овсяное молоко 1.5 ", ["свежий хлеб 2", "овсяное молоко 1.5"]),
            (" ".join(f"coffee {i}" for i in range(1, 21)), [f"coffee {i}" for i in range(1, 21)]),
        ):
            with self.subTest(text=text):
                self.assertEqual(split_multi_expenses(text), expected)

    def test_rejects_entire_invalid_or_ambiguous_expression(self):
        for text in (
            "кофе 3 булочка", "кофе 3 булочка x", "кофе 3 булочка 2.50 остаток",
            "кофе 3 булочка -2", "кофе 3 булочка +2", "кофе 3 булочка 0",
            "кофе 3 булочка 2.500", "кофе 3 булочка 2..5", "кофе 3 булочка 02",
            "10 пицца 20", "кофе 3 2 булочка", "витамин B12 9 хлеб 2",
            "7up 3 хлеб 2", "билет 28.09.2026 9 кофе 3", "билет 28/09 9 кофе 3",
            "телефон 49123456789 кофе 3", "хлеб 2 кг 5", "coffee 2 pcs 5",
            "iPhone 15 чехол 20", "витамин 12 хлеб 2", "дата 12.05 кофе 3",
            "кофе 3 € хлеб 2", "кофе 3 eur 2", "краска 45 кисть 3 #ремонт",
        ):
            with self.subTest(text=text):
                self.assertIsNone(split_multi_expenses(text))

    def test_single_formats_remain_on_original_parser(self):
        for text, kind, amount in (
            ("кофе 3.50", "expense", 3.5), ("7.22 пицца", "expense", 7.22),
            ("зарплата +2300", "income", 2300), ("+150 возврат", "income", 150),
            ("++500", "goal_contribution", 500),
        ):
            with self.subTest(text=text):
                self.assertIsNone(split_multi_expenses(text))
                parsed = parse_message(text)
                self.assertEqual((parsed["type"], parsed["amount"]), (kind, amount))
        self.assertIsNone(split_multi_expenses("краска 45 #ремонт"))


class MultiExpenseHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.family = SimpleNamespace(id=7, language="ru", currency="EUR")
        self.user = SimpleNamespace(id=3, family_id=7)
        self.message = SimpleNamespace(text="", from_user=SimpleNamespace(id=10),
            chat=SimpleNamespace(id=100, type="private"), answer=AsyncMock(),
            bot=SimpleNamespace(token="test-signing-key"))
        self.state = AsyncMock()
        self.stack.enter_context(patch.object(expenses, "require_family_for_chat", AsyncMock(return_value=self.family)))
        self.stack.enter_context(patch.object(expenses, "get_user_by_telegram_id", AsyncMock(return_value=self.user)))
        self.stack.enter_context(patch.object(expense_service, "get_user_by_telegram_id", AsyncMock(return_value=self.user)))
        self.catalog = category_override_service._build_catalog([])
        self.stack.enter_context(patch.object(category_override_service, "get_effective_category_catalog",
                                             AsyncMock(return_value=self.catalog)))
        self.custom = self.stack.enter_context(patch.object(custom_category_service, "list_custom_categories",
                                                           AsyncMock(return_value=[])))
        self.classify = self.stack.enter_context(patch.object(expense_service, "detect_category_reference_for_family",
            wraps=expense_service.detect_category_reference_for_family))
        self.saved = []
        self.engine = create_engine("sqlite:///:memory:")
        self.addCleanup(self.engine.dispose)
        # Copy metadata so PostgreSQL-specific defaults can be omitted only
        # in this ephemeral test schema, without modifying application models.
        metadata = MetaData()
        for table in Base.metadata.tables.values():
            table.to_metadata(metadata)
        tables = [metadata.tables[model.__tablename__] for model in (Family, FamilyCategory, Transaction)]
        for table in tables:
            for column in table.columns:
                if column.server_default is not None and "AT TIME ZONE" in str(column.server_default.arg):
                    column.server_default = None
        metadata.create_all(self.engine, tables=tables)
        with Session(self.engine) as session:
            session.add(Family(id=7, name="Test", invite_code="batch-test"))
            session.commit()
        self.sessions = []

        def session_factory():
            session = SQLiteSession(self.engine, self.saved)
            self.sessions.append(session)
            return session

        self.stack.enter_context(patch.object(expense_service, "SessionLocal", side_effect=session_factory))
        self.stack.enter_context(patch.object(bulk_undo_service, "SessionLocal", side_effect=session_factory))
        self.batch = self.stack.enter_context(patch.object(
            expenses, "save_transaction_batch", wraps=expense_service.save_transaction_batch,
        ))

        async def create(**values):
            transaction = SimpleNamespace(id=len(self.saved) + 1, type=values.pop("transaction_type"), **values)
            self.saved.append(transaction)
            return transaction

        self.create = self.stack.enter_context(patch.object(expense_service, "create_transaction", AsyncMock(side_effect=create)))
        self.save = self.stack.enter_context(patch.object(expenses, "save_transaction", wraps=expense_service.save_transaction))

    async def send(self, text):
        self.message.text = text
        await expenses.add_transaction(self.message, self.state)

    def bulk_callback(self):
        markup = self.message.answer.await_args.kwargs["reply_markup"]
        self.assertEqual([len(row) for row in markup.inline_keyboard], [1])
        button = markup.inline_keyboard[0][0]
        self.assertEqual(button.text, "↩️ Отменить операции")
        self.assertLessEqual(len(button.callback_data.encode()), 64)
        data = UndoBatchCallback.unpack(button.callback_data)
        callback = SimpleNamespace(
            from_user=self.message.from_user, bot=self.message.bot, answer=AsyncMock(),
            message=SimpleNamespace(chat=self.message.chat, edit_text=AsyncMock(),
                                    edit_reply_markup=AsyncMock()),
        )
        return callback, data

    def remaining_ids(self):
        with Session(self.engine) as session:
            return list(session.scalars(select(Transaction.id).order_by(Transaction.id)))

    async def test_bulk_button_deletes_exact_two_after_menu_and_double_click_is_safe(self):
        await self.send("Бензин 9 продуктов 60")
        callback, data = self.bulk_callback()
        self.assertEqual(len(self.remaining_ids()), 2)
        # Undo has no dependency on a live FSM or the original handler session.
        await self.state.clear()
        with Session(self.engine) as session:
            other = Transaction(user_id=3, family_id=7, title="Other input", amount=20,
                                type="expense", category="Other", is_recurring=False)
            session.add(other)
            session.commit()
            other_id = other.id
        await expenses.undo_batch_callback(callback, data)
        self.assertEqual(self.remaining_ids(), [other_id])
        callback.message.edit_text.assert_awaited_once_with(t("ru", "undo.batch_done"), reply_markup=None)
        callback.answer.assert_awaited_once_with()
        callback.answer.reset_mock()
        await expenses.undo_batch_callback(callback, data)
        callback.answer.assert_awaited_once_with(t("ru", "undo.batch_stale"), show_alert=True)
        self.assertEqual(self.remaining_ids(), [other_id])

    async def test_bulk_button_deletes_three(self):
        await self.send("хлеб 2 молоко 1.50 сыр 4")
        callback, data = self.bulk_callback()
        self.assertEqual(len(self.remaining_ids()), 3)
        self.assertEqual(len({row.created_at for row in self.saved}), 1)
        await expenses.undo_batch_callback(callback, data)
        self.assertEqual(self.remaining_ids(), [])

    async def test_bulk_delete_second_failure_rolls_back_and_can_be_retried(self):
        await self.send("хлеб 2 молоко 1.50 сыр 4")
        callback, data = self.bulk_callback()
        original_ids = self.remaining_ids()
        with Session(self.engine) as session:
            activity = session.get(Family, 7).last_activity_at
        deleted = 0

        async def failing_delete(adapter, row):
            nonlocal deleted
            adapter.session.delete(row)
            adapter.session.flush()  # Prove rollback of an already issued DELETE.
            deleted += 1
            if deleted == 2:
                raise SQLAlchemyError("Injected second delete failure")

        with patch.object(SQLiteSession, "delete", failing_delete):
            await expenses.undo_batch_callback(callback, data)
        self.assertEqual(deleted, 2)
        self.assertEqual(self.remaining_ids(), original_ids)
        with Session(self.engine) as session:
            self.assertEqual(session.get(Family, 7).last_activity_at, activity)
        callback.answer.assert_awaited_once_with(t("ru", "undo.batch_error"), show_alert=True)
        callback.message.edit_text.assert_not_awaited()
        await expenses.undo_batch_callback(callback, data)
        self.assertEqual(self.remaining_ids(), [])

    async def test_bulk_commit_failure_rolls_back(self):
        await self.send("хлеб 2 молоко 3")
        callback, data = self.bulk_callback()
        original_ids = self.remaining_ids()

        def fail_commit(session):
            raise SQLAlchemyError("Injected commit failure")

        event.listen(Session, "before_commit", fail_commit)
        try:
            await expenses.undo_batch_callback(callback, data)
        finally:
            event.remove(Session, "before_commit", fail_commit)
        self.assertEqual(self.remaining_ids(), original_ids)
        callback.answer.assert_awaited_once_with(t("ru", "undo.batch_error"), show_alert=True)

    async def test_activity_failure_after_delete_flush_rolls_back(self):
        await self.send("хлеб 2 молоко 3")
        callback, data = self.bulk_callback()
        original_ids = self.remaining_ids()
        with patch.object(bulk_undo_service, "touch_family_activity",
                          AsyncMock(side_effect=SQLAlchemyError("Activity failed"))):
            await expenses.undo_batch_callback(callback, data)
        self.assertEqual(self.remaining_ids(), original_ids)
        callback.answer.assert_awaited_once_with(t("ru", "undo.batch_error"), show_alert=True)

    async def test_bulk_other_family_or_author_cannot_delete(self):
        await self.send("хлеб 2 молоко 3")
        callback, data = self.bulk_callback()
        original_ids = self.remaining_ids()
        for family_id, user_id, expected in ((8, 3, "forbidden"), (7, 9, "not_author")):
            with self.subTest(family=family_id, author=user_id):
                result = await bulk_undo_service.undo_transaction_batch(
                    data.first_id, data.last_id, data.signature, family_id, user_id,
                    self.message.bot.token,
                )
                self.assertEqual(result.status, expected)
                self.assertEqual(self.remaining_ids(), original_ids)
        self.family.id = self.user.family_id = 8
        await expenses.undo_batch_callback(callback, data)
        callback.answer.assert_awaited_once_with(t("ru", "undo.forbidden"), show_alert=True)
        self.assertEqual(self.remaining_ids(), original_ids)

    async def test_bulk_tampered_signature_bounds_and_signing_key_delete_nothing(self):
        await self.send("хлеб 2 молоко 3")
        _, data = self.bulk_callback()
        original_ids = self.remaining_ids()
        for first, last, signature, key in (
            (data.first_id, data.last_id, "x" * 22, self.message.bot.token),
            (data.first_id, data.last_id + 1, "x" * 22, self.message.bot.token),
            (data.first_id, data.last_id + 1, data.signature, self.message.bot.token),
            (data.first_id, data.last_id, data.signature, "wrong-key"),
            (-1, data.last_id, data.signature, self.message.bot.token),
        ):
            result = await bulk_undo_service.undo_transaction_batch(first, last, signature, 7, 3, key)
            self.assertNotEqual(result.status, "deleted")
            self.assertEqual(self.remaining_ids(), original_ids)

    async def test_missing_middle_member_never_deletes_remainder(self):
        await self.send("хлеб 2 молоко 3 сыр 4")
        callback, data = self.bulk_callback()
        with Session(self.engine) as session:
            session.delete(session.get(Transaction, self.saved[1].id))
            session.commit()
        remaining = self.remaining_ids()
        await expenses.undo_batch_callback(callback, data)
        self.assertEqual(self.remaining_ids(), remaining)
        callback.answer.assert_awaited_once_with(t("ru", "undo.batch_stale"), show_alert=True)

    async def test_changed_member_ownership_or_recurring_status_blocks_entire_batch(self):
        await self.send("хлеб 2 молоко 3 сыр 4")
        callback, data = self.bulk_callback()
        original_ids = self.remaining_ids()
        for field, changed, original in (("family_id", 8, 7), ("user_id", 9, 3),
                                          ("is_recurring", True, False)):
            with self.subTest(field=field):
                with Session(self.engine) as session:
                    setattr(session.get(Transaction, self.saved[1].id), field, changed)
                    session.commit()
                await expenses.undo_batch_callback(callback, data)
                self.assertEqual(self.remaining_ids(), original_ids)
                with Session(self.engine) as session:
                    setattr(session.get(Transaction, self.saved[1].id), field, original)
                    session.commit()

    async def test_bulk_ttl_matches_single_undo(self):
        await self.send("хлеб 2 молоко 3")
        _, data = self.bulk_callback()
        created = self.saved[0].created_at
        result = await bulk_undo_service.undo_transaction_batch(
            data.first_id, data.last_id, data.signature, 7, 3, self.message.bot.token,
            now=created + timedelta(seconds=61),
        )
        self.assertEqual(result.status, "expired")
        self.assertEqual(len(self.remaining_ids()), 2)
        result = await bulk_undo_service.undo_transaction_batch(
            data.first_id, data.last_id, data.signature, 7, 3, self.message.bot.token,
            now=created + timedelta(seconds=60),
        )
        self.assertEqual(result.status, "deleted")

    async def test_bulk_59_seconds_and_clock_anomalies(self):
        await self.send("хлеб 2 молоко 3")
        callback, data = self.bulk_callback()
        original_ids = self.remaining_ids()
        created = self.saved[0].created_at
        for offset in (timedelta(microseconds=-1), timedelta(days=-1),
                       timedelta(seconds=60, microseconds=1), timedelta(days=1)):
            result = await bulk_undo_service.undo_transaction_batch(
                data.first_id, data.last_id, data.signature, 7, 3, self.message.bot.token,
                now=created + offset,
            )
            self.assertEqual(result.status, "expired")
            self.assertEqual(self.remaining_ids(), original_ids)
        result = await bulk_undo_service.undo_transaction_batch(
            data.first_id, data.last_id, data.signature, 7, 3, self.message.bot.token,
            now=created + timedelta(seconds=59),
        )
        self.assertEqual(result.status, "deleted")
        await expenses.undo_batch_callback(callback, data)
        callback.answer.assert_awaited_once_with(t("ru", "undo.batch_stale"), show_alert=True)

    async def test_malformed_callback_filter_rejects_without_exception(self):
        callback_filter = UndoBatchCallback.filter()
        for payload in (None, "", "undo_batch", "undo_batch:1:2",
                        "undo_batch:no:2:sig", "undo_batch:1:2:sig:extra"):
            query = CallbackQuery(id="review", from_user=TelegramUser(id=10, is_bot=False,
                                  first_name="Test"), chat_instance="test", data=payload)
            self.assertFalse(await callback_filter(query))
        await self.send("хлеб 2 молоко 3")
        callback, data = self.bulk_callback()
        original_ids = self.remaining_ids()
        for signature in ("", "short", "я" * 22):
            await expenses.undo_batch_callback(callback, data.model_copy(update={"signature": signature}))
            self.assertEqual(self.remaining_ids(), original_ids)
        self.assertEqual(callback.answer.await_count, 3)

    async def test_two_batches_with_interleaved_ids_and_near_identical_timestamps(self):
        created = datetime.now(timezone.utc).replace(tzinfo=None)
        with Session(self.engine, expire_on_commit=False) as session:
            rows = [Transaction(id=i, user_id=3, family_id=7, title=title, amount=amount,
                                type="expense", category="Other", is_recurring=False,
                                created_at=created + timedelta(microseconds=i % 2))
                    for i, title, amount in ((101, "бензин", 9), (102, "кофе", 3),
                                             (103, "продукты", 60), (104, "булочка", 2))]
            session.add_all(rows)
            session.commit()
        for batch, remaining in (([rows[0], rows[2]], [102, 104]), ([rows[1], rows[3]], [])):
            signature = bulk_undo_service.batch_signature(batch, self.message.bot.token)
            result = await bulk_undo_service.undo_transaction_batch(
                batch[0].id, batch[-1].id, signature, 7, 3, self.message.bot.token,
            )
            self.assertEqual(result.status, "deleted")
            self.assertEqual(self.remaining_ids(), remaining)

    async def test_two_simultaneous_callbacks_serialize_delete_and_answer_both(self):
        await self.send("хлеб 2 молоко 3")
        first, data = self.bulk_callback()
        second, _ = self.bulk_callback()
        store = {row.id: row for row in self.saved}
        unrelated_id = data.last_id + 10
        store[unrelated_id] = SimpleNamespace(id=unrelated_id)
        row_lock = asyncio.Lock()
        anchors_ready = asyncio.Event()
        anchors_read = 0
        delete_commits = []
        case = self

        class ConcurrentSession:
            """Model READ COMMITTED: both read anchor, second SELECT waits
            for row locks, then observes deletion committed by the first.
            Actual PostgreSQL is intentionally not contacted in this test.
            """
            def __init__(self):
                self.pending = []
                self.active = False
                self.locked = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            @asynccontextmanager
            async def begin(self):
                self.active = True
                try:
                    yield
                    if self.pending:
                        for row_id in self.pending:
                            del store[row_id]
                        delete_commits.append(list(self.pending))
                finally:
                    self.active = False
                    if self.locked:
                        row_lock.release()

            async def scalar(self, statement):
                nonlocal anchors_read
                case.assertTrue(self.active)
                anchor = store.get(data.first_id)
                anchors_read += 1
                if anchors_read == 2:
                    anchors_ready.set()
                await anchors_ready.wait()
                return anchor

            async def execute(self, statement):
                case.assertTrue(self.active)
                compiled = str(statement.compile(dialect=postgresql.dialect()))
                case.assertIn("ORDER BY transactions.id FOR UPDATE", compiled)
                await row_lock.acquire()
                self.locked = True
                rows = [store[i] for i in sorted(store) if data.first_id <= i <= data.last_id]
                return SimpleNamespace(scalars=lambda: rows)

            async def delete(self, row):
                case.assertTrue(self.active and self.locked)
                self.pending.append(row.id)

            async def flush(self):
                case.assertTrue(self.active and self.locked)

        with patch.object(bulk_undo_service, "SessionLocal", side_effect=ConcurrentSession), \
             patch.object(bulk_undo_service, "touch_family_activity", AsyncMock()):
            await asyncio.wait_for(asyncio.gather(
                expenses.undo_batch_callback(first, data),
                expenses.undo_batch_callback(second, data),
            ), timeout=5)
        self.assertEqual(anchors_read, 2)
        self.assertEqual(delete_commits, [[data.first_id, data.last_id]])
        self.assertEqual(list(store), [unrelated_id])
        answers = [first.answer.await_args, second.answer.await_args]
        self.assertCountEqual([call.args for call in answers], [(), (t("ru", "undo.batch_stale"),)])
        first.answer.assert_awaited_once()
        second.answer.assert_awaited_once()
        self.assertEqual(first.message.edit_text.await_count + second.message.edit_text.await_count, 1)

    def test_bulk_i18n_keys_exist_in_every_locale(self):
        for language in SUPPORTED_LANGUAGES:
            for key in ("undo.batch_button", "undo.batch_done", "undo.batch_stale", "undo.batch_error",
                        "undo.expired", "undo.author_only", "undo.forbidden"):
                self.assertNotEqual(t(language, key), key)
                self.assertTrue(t(language, key).strip())

    def test_postgresql_timestamp_has_microsecond_precision(self):
        timestamp_type = Transaction.__table__.c.created_at.type.compile(dialect=postgresql.dialect())
        self.assertEqual(timestamp_type, "TIMESTAMP WITHOUT TIME ZONE")

    async def test_uneditable_confirmation_still_answers_callback(self):
        await self.send("хлеб 2 молоко 3")
        callback, data = self.bulk_callback()
        error = TelegramBadRequest(method=EditMessageText(text="Undo"), message="not found")
        callback.message.edit_text.side_effect = error
        callback.message.edit_reply_markup.side_effect = error
        await expenses.undo_batch_callback(callback, data)
        callback.answer.assert_awaited_once_with()
        self.assertEqual(self.remaining_ids(), [])

    async def test_inaccessible_confirmation_is_safe_noop(self):
        await self.send("хлеб 2 молоко 3")
        callback, data = self.bulk_callback()
        original_ids = self.remaining_ids()
        callback.message = InaccessibleMessage(chat=Chat(id=10, type="private"), message_id=1, date=0)
        with patch.object(expenses, "undo_transaction_batch", AsyncMock()) as undo:
            for _ in range(2):
                await expenses.undo_batch_callback(callback, data)
            undo.assert_not_awaited()
        self.assertEqual(callback.answer.await_count, 2)
        self.assertEqual(self.remaining_ids(), original_ids)

    async def test_single_games_keeps_single_undo_callback(self):
        await self.send("Игры 20")
        markup = self.message.answer.await_args.kwargs["reply_markup"]
        self.assertEqual(markup.inline_keyboard[0][0].text, "↩️ Отменить операцию")
        data = UndoOperationCallback.unpack(markup.inline_keyboard[0][0].callback_data)
        self.assertEqual((data.kind, data.operation_id), ("transaction", self.saved[0].id))
        self.batch.assert_not_awaited()

    async def test_noncontiguous_ids_exclude_interleaved_input(self):
        created = datetime.now(timezone.utc).replace(tzinfo=None)
        with Session(self.engine, expire_on_commit=False) as session:
            rows = [Transaction(id=i, user_id=3, family_id=7, title="Test", amount=2,
                                type="expense", category="Other", is_recurring=False,
                                created_at=created if i != 102 else created + timedelta(microseconds=1))
                    for i in (101, 102, 103)]
            session.add_all(rows)
            session.commit()
        signature = bulk_undo_service.batch_signature([rows[0], rows[2]], self.message.bot.token)
        result = await bulk_undo_service.undo_transaction_batch(101, 103, signature, 7, 3, self.message.bot.token)
        self.assertEqual(result.status, "deleted")
        self.assertEqual(self.remaining_ids(), [102])

    async def test_timestamp_collision_cannot_add_unrelated_row_to_batch(self):
        created = datetime.now(timezone.utc).replace(tzinfo=None)
        with Session(self.engine, expire_on_commit=False) as session:
            rows = [Transaction(id=i, user_id=3, family_id=7, title="Test", amount=2,
                                type="expense", category="Other", is_recurring=False,
                                created_at=created) for i in (101, 102, 103)]
            session.add_all(rows)
            session.commit()
        signature = bulk_undo_service.batch_signature([rows[0], rows[2]], self.message.bot.token)
        result = await bulk_undo_service.undo_transaction_batch(101, 103, signature, 7, 3, self.message.bot.token)
        self.assertEqual(result.status, "already_deleted")
        self.assertEqual(self.remaining_ids(), [101, 102, 103])

    def test_callback_length_independent_of_batch_size(self):
        created = datetime(2026, 9, 29)
        for count in (2, 3, 10, 1000):
            for first_id in (1, 1_900_000_000, 2**31 - count):
                rows = [SimpleNamespace(id=first_id + i, family_id=7, user_id=3, created_at=created)
                        for i in range(count)]
                signature = bulk_undo_service.batch_signature(rows, self.message.bot.token)
                markup = undo_batch_keyboard(rows[0].id, rows[-1].id, signature)
                size = len(markup.inline_keyboard[0][0].callback_data.encode("utf-8"))
                self.assertEqual(size, 35 + len(str(first_id)) + len(str(first_id + count - 1)))
                self.assertLessEqual(size, 55)

    async def test_two_expenses_classified_independently_and_one_bulk_confirmation(self):
        await self.send("Бензин 9 продукты 60")
        self.assertEqual([(x.title, x.amount, x.type) for x in self.saved],
                         [("Бензин", 9, "expense"), ("продукты", 60, "expense")])
        self.assertNotEqual(self.saved[0].category, self.saved[1].category)
        self.assertEqual(self.saved[1].category, "🛒 Продукты")
        self.assertEqual([call.args for call in self.classify.await_args_list],
                         [(7, "Бензин", "expense"), (7, "продукты", "expense")])
        self.assertTrue(all(x.family_id == 7 and x.user_id == 3 for x in self.saved))
        self.message.answer.assert_awaited_once()
        text = self.message.answer.await_args.args[0]
        self.assertIn(t("ru", "quick.saved", count=2), text)
        self.assertIn("69.00", text)
        keyboard = self.message.answer.await_args.kwargs["reply_markup"]
        self.assertEqual([len(row) for row in keyboard.inline_keyboard], [1])
        self.assertEqual(keyboard.inline_keyboard[0][0].text, "↩️ Отменить операции")
        data = UndoBatchCallback.unpack(keyboard.inline_keyboard[0][0].callback_data)
        self.assertEqual((data.first_id, data.last_id), (self.saved[0].id, self.saved[1].id))
        self.batch.assert_awaited_once_with(["Бензин 9", "продукты 60"], 10, 7)
        self.save.assert_not_awaited()
        self.create.assert_not_awaited()
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Transaction)), 2)
            self.assertIsNotNone(session.get(Family, 7).last_activity_at)

    async def test_three_expenses_and_decimal_comma(self):
        await self.send("хлеб 2 молоко 1,50 сыр 4")
        self.assertEqual([x.amount for x in self.saved], [2, 1.5, 4])

    async def test_decimal_dot_and_localized_confirmation(self):
        self.family.language = "en"
        await self.send("кофе 3 булочка 2.50")
        self.assertEqual([x.amount for x in self.saved], [3, 2.5])
        text = self.message.answer.await_args.args[0]
        self.assertIn(t("en", "quick.saved", count=2), text)
        self.assertIn(t("en", "quick.expense"), text)

    async def test_invalid_expression_creates_nothing_including_multiline_prefix(self):
        for text in ("кофе 3 булочка x", "кофе 3 булочка 2.500", "кофе 3 булочка 2 хвост",
                     "кофе 3 хлеб 2\nмолоко x", "кофе 3\nхлеб 2 молоко x",
                     "кофе 3 хлеб 2 #ремонт", "кофе 3 хлеб 2\nкраска 45 #ремонт",
                     "кофе 3\nкраска 45 кисть 3 #ремонт",
                     "iPhone 15 чехол 20", "дата 12.05 кофе 3", "хлеб 2 кг 5"):
            with self.subTest(text=text):
                await self.send(text)
                self.create.assert_not_awaited()
                self.batch.assert_not_awaited()
                self.assertIn(t("ru", "quick.unrecognized"), self.message.answer.await_args.args[0])

    async def test_family_override_and_custom_category_are_applied_per_pair(self):
        self.catalog["animals"].append(SimpleNamespace(normalized_keyword="груминг"))
        custom = SimpleNamespace(id=17, icon="🎬", name="Family movies",
                                 keywords=[SimpleNamespace(normalized_keyword="кино")])
        self.custom.return_value = [custom]
        with Session(self.engine) as session:
            session.add(FamilyCategory(id=17, family_id=7, name=custom.name,
                                       normalized_name="family movies", icon=custom.icon))
            session.commit()
        await self.send("груминг 20 кино 12")
        animals = CATEGORIES["animals"]
        self.assertEqual(self.saved[0].category, f"{animals['icon']} {animals['title']}")
        self.assertEqual(self.saved[1].category, "🎬 Family movies")
        self.assertEqual(self.saved[1].custom_category_id, 17)

    async def test_single_project_still_uses_existing_project_resolution(self):
        project = SimpleNamespace(id=42, name="Ремонт", is_active=True)
        with patch.object(expense_service, "find_family_project_by_tag", AsyncMock(return_value=project)) as find:
            await self.send("краска 45 #ремонт")
        find.assert_awaited_once_with(7, "ремонт")
        self.save.assert_awaited_once_with("краска 45 #ремонт", 10, 7)
        self.assertEqual(self.saved[0].project_id, 42)

    async def test_numeric_project_tag_remains_single_transaction(self):
        project = SimpleNamespace(id=42, name="Year", is_active=True)
        with patch.object(expense_service, "find_family_project_by_tag", AsyncMock(return_value=project)) as find:
            await self.send("краска 45 #2026")
        find.assert_awaited_once_with(7, "2026")
        self.assertEqual(len(self.saved), 1)

    async def test_single_and_income_preserve_original_service_input_and_undo(self):
        for text, kind in (("кофе 3.50", "expense"), ("7.22 пицца", "expense"),
                           ("зарплата +2300", "income"), ("+150 возврат", "income")):
            await self.send(text)
            self.assertEqual(self.save.await_args.args, (text, 10, 7))
            self.assertEqual(self.saved[-1].type, kind)
            self.assertTrue(hasattr(self.message.answer.await_args.kwargs["reply_markup"], "inline_keyboard"))
        self.batch.assert_not_awaited()

    async def test_goal_contribution_never_enters_transaction_service(self):
        with patch.object(expenses, "add_contribution", AsyncMock(return_value=None)) as goal:
            await self.send("++500")
        goal.assert_awaited_once_with(7, 10, 500)
        self.save.assert_not_awaited()
        self.create.assert_not_awaited()
        self.batch.assert_not_awaited()

    def assert_nothing_persisted(self):
        self.assertEqual(self.saved, [])
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Transaction)), 0)
            self.assertIsNone(session.get(Family, 7).last_activity_at)

    async def test_insert_failure_on_second_or_third_rolls_back_entire_batch(self):
        for failing_insert in (2, 3):
            with self.subTest(failing_insert=failing_insert):
                count = 0

                def fail_insert(connection, cursor, statement, parameters, context, executemany):
                    nonlocal count
                    if statement.startswith("INSERT INTO transactions"):
                        count += 1
                        if count == failing_insert:
                            raise SQLAlchemyError("Injected insert failure")

                event.listen(self.engine, "before_cursor_execute", fail_insert)
                try:
                    with self.assertRaises(SQLAlchemyError):
                        await self.send("хлеб 2 молоко 1,50 сыр 4")
                finally:
                    event.remove(self.engine, "before_cursor_execute", fail_insert)
                self.assertEqual(count, failing_insert)
                self.assert_nothing_persisted()
                self.message.answer.assert_not_awaited()

    async def test_commit_failure_rolls_back_rows_and_family_activity(self):
        def fail_commit(session):
            raise SQLAlchemyError("Injected commit failure")

        event.listen(Session, "before_commit", fail_commit)
        try:
            with self.assertRaises(SQLAlchemyError):
                await self.send("хлеб 2 молоко 1,50 сыр 4")
        finally:
            event.remove(Session, "before_commit", fail_commit)
        self.assert_nothing_persisted()
        self.message.answer.assert_not_awaited()

    async def test_classification_failure_creates_nothing(self):
        self.classify.side_effect = [("🛒", "Продукты", None), SQLAlchemyError("Classifier failed")]
        with self.assertRaises(SQLAlchemyError):
            await self.send("хлеб 2 молоко 1,50 сыр 4")
        self.assertEqual(self.sessions, [])
        self.assert_nothing_persisted()

    async def test_invalid_custom_category_rolls_back_everything(self):
        for family_id, active in ((8, True), (7, False)):
            with self.subTest(family_id=family_id, active=active):
                with Session(self.engine) as session:
                    old = session.get(FamilyCategory, 17)
                    if old is not None:
                        old.family_id = family_id
                        old.is_active = active
                    else:
                        session.add(FamilyCategory(id=17, family_id=family_id, name="Movies",
                            normalized_name="movies", icon="🎬", is_active=active))
                    session.commit()
                self.classify.side_effect = [("🛒", "Продукты", None), ("🎬", "Movies", 17)]
                await self.send("хлеб 2 кино 12")
                self.assert_nothing_persisted()
                self.assertIn(t("ru", "quick.unrecognized"), self.message.answer.await_args.args[0])

    async def test_batch_service_validates_all_input_and_user_before_writing(self):
        for lines in (["хлеб 2", "молоко x"], ["хлеб 2", "++500"],
                      ["хлеб 2", "краска 45 #ремонт"], ["хлеб 2", "молоко 0"],
                      ["хлеб 2", "x" * 256 + " 3"]):
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                await expense_service.save_transaction_batch(lines, 10, 7)
        self.user.family_id = 8
        with self.assertRaises(ValueError):
            await expense_service.save_transaction_batch(["хлеб 2", "молоко 3"], 10, 7)
        self.assertEqual(self.sessions, [])
        self.assert_nothing_persisted()

    async def test_multi_and_single_lines_share_one_transaction(self):
        await self.send("хлеб 2 молоко 3\nсыр 4\n+150 возврат")
        self.assertEqual([item.type for item in self.saved], ["expense"] * 3 + ["income"])
        self.assertEqual(len(self.sessions), 1)
        self.save.assert_not_awaited()
        self.message.answer.assert_awaited_once()

    async def test_goal_mixed_with_multi_rejected_before_any_save(self):
        with patch.object(expenses, "add_contribution", AsyncMock()) as goal:
            for text in ("++500\nхлеб 2 молоко 3", "хлеб 2 молоко 3\n++500"):
                await self.send(text)
        goal.assert_not_awaited()
        self.save.assert_not_awaited()
        self.batch.assert_not_awaited()
        self.assert_nothing_persisted()
