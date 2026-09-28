import unittest
from contextlib import ExitStack, asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import MetaData, create_engine, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.db import Base
from app.database.models import Family, FamilyCategory, Transaction
from app.data.categories import CATEGORIES
from app.handlers import expenses
from app.i18n import t
from app.keyboards.main_menu import back_to_main_menu
from app.services import category_override_service, custom_category_service, expense_service
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
            chat=SimpleNamespace(id=100, type="private"), answer=AsyncMock())
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
        self.assertEqual(self.message.answer.await_args.kwargs["reply_markup"], back_to_main_menu("ru"))
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
