import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import UniqueConstraint

from app.database.models import Project, Transaction
from app.handlers import expenses, projects
from app.handlers.project_states import ProjectState, ProjectTransactionState
from app.keyboards.projects import ProjectCallback
from app.keyboards.projects import projects_keyboard
from app.services import expense_service, project_service
from app.services.parser import parse_message


class Result:
    def __init__(self, scalar=None, scalars=None, row=None):
        self._scalar = scalar
        self._scalars = scalars or []
        self._row = row

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar

    def scalars(self):
        return self._scalars

    def one(self):
        return self._row


class Session:
    def __init__(self, results):
        self.results = list(results)
        self.added = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, _statement):
        return self.results.pop(0)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass

    async def refresh(self, _value):
        pass


class State:
    def __init__(self, data=None):
        self.data = data or {}
        self.value = None
        self.cleared = False

    async def update_data(self, **kwargs):
        self.data.update(kwargs)

    async def get_data(self):
        return self.data

    async def set_state(self, value):
        self.value = value

    async def clear(self):
        self.value = None
        self.cleared = True


class Message:
    def __init__(self, text=""):
        self.text = text
        self.from_user = SimpleNamespace(id=100)
        self.chat = SimpleNamespace(id=500)
        self.answers = []
        self.edits = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))

    async def edit_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class Callback:
    def __init__(self):
        self.from_user = SimpleNamespace(id=100)
        self.message = Message()
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))


class ProjectModelTests(unittest.TestCase):
    def test_project_schema_and_transaction_nullable_project(self):
        columns = Project.__table__.c
        self.assertEqual(set(columns.keys()), {"id", "family_id", "name", "tag", "is_active", "created_at"})
        self.assertFalse(columns.family_id.nullable)
        self.assertEqual(columns.name.type.length, 100)
        self.assertEqual(columns.tag.type.length, 30)
        self.assertTrue(Transaction.__table__.c.project_id.nullable)
        self.assertEqual(Transaction.__table__.c.category.type.length, 100)

    def test_tag_is_unique_only_inside_family(self):
        constraints = [item for item in Project.__table__.constraints if isinstance(item, UniqueConstraint)]
        self.assertIn(("family_id", "tag"), [tuple(column.name for column in item.columns) for item in constraints])

    def test_migration_is_additive(self):
        source = open("docs/migrations/20260808_add_projects.sql", encoding="utf-8").read().lower()
        self.assertIn("create table projects", source)
        self.assertIn("add column project_id integer null", source)
        self.assertNotIn("delete from", source)
        self.assertNotIn("update transactions", source)

    def test_project_list_paginates_by_ten(self):
        values = [SimpleNamespace(id=i, name=f"P{i}", tag=f"tag{i}") for i in range(1, 11)]
        keyboard = projects_keyboard(values, total=11, page=0, active=True)
        self.assertEqual(len(keyboard.inline_keyboard[:10]), 10)
        self.assertTrue(any(button.text == "➡️" for row in keyboard.inline_keyboard for button in row))


class ProjectValidationTests(unittest.TestCase):
    def test_name_validation(self):
        self.assertEqual(project_service.validate_project_name("  Дача  "), "Дача")
        for value in ("", " " * 3, "x" * 101, "/start"):
            with self.assertRaises(ValueError):
                project_service.validate_project_name(value)

    def test_tag_normalization_and_validation(self):
        self.assertEqual(project_service.normalize_project_tag(" #Дача "), "дача")
        self.assertEqual(project_service.normalize_project_tag("ITALY26"), "italy26")
        for value in ("a", "x" * 31, "да ча", "tag_1", "#", "/tag"):
            with self.assertRaises(ValueError):
                project_service.normalize_project_tag(value)

    def test_tag_parser_is_optional_and_removes_only_final_tag(self):
        self.assertEqual(project_service.extract_project_tag("кофе 20"), ("кофе 20", None))
        self.assertEqual(project_service.extract_project_tag("кофе 20 #Дача"), ("кофе 20", "дача"))
        with self.assertRaises(ValueError):
            project_service.extract_project_tag("кофе 20 #дача #отпуск")

    def test_old_category_parser_is_unchanged(self):
        plain = parse_message("кофе 20")
        cleaned, tag = project_service.extract_project_tag("кофе 20 #дача")
        tagged = parse_message(cleaned)
        self.assertEqual(tag, "дача")
        self.assertEqual(tagged, plain)


class ProjectServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_project_normalizes_and_touches_activity(self):
        session = Session([Result(scalar=7)])
        with patch.object(project_service, "SessionLocal", return_value=session), \
             patch.object(project_service, "touch_family_activity", AsyncMock()) as touch:
            project = await project_service.create_project(100, " Дача ", "#Дача")
        self.assertEqual((project.family_id, project.name, project.tag), (7, "Дача", "дача"))
        touch.assert_awaited_once_with(7, session=session)
        self.assertTrue(session.committed)

    async def test_foreign_project_is_not_returned_or_updated(self):
        session = Session([Result(scalar=7), Result(scalar=None)])
        with patch.object(project_service, "SessionLocal", return_value=session), \
             patch.object(project_service, "touch_family_activity", AsyncMock()) as touch:
            result = await project_service.update_project_name(100, 999, "Новое")
        self.assertIsNone(result)
        touch.assert_not_awaited()

    async def test_rename_retag_finish_and_resume_touch_activity(self):
        project = SimpleNamespace(id=2, family_id=7, name="Дача", tag="дача", is_active=True)
        operations = (
            (project_service.update_project_name, " Новая дача ", "name", "Новая дача"),
            (project_service.update_project_tag, "#Лето26", "tag", "лето26"),
            (project_service.set_project_active, False, "is_active", False),
            (project_service.set_project_active, True, "is_active", True),
        )
        for function, value, field, expected in operations:
            session = Session([Result(scalar=7), Result(scalar=project)])
            with patch.object(project_service, "SessionLocal", return_value=session), \
                 patch.object(project_service, "touch_family_activity", AsyncMock()) as touch:
                updated = await function(100, 2, value)
            self.assertIs(updated, project)
            self.assertEqual(getattr(project, field), expected)
            touch.assert_awaited_once_with(7, session=session)

    async def test_project_statistics_include_expenses_only(self):
        project = SimpleNamespace(id=2, family_id=7)
        session = Session([Result(scalar=7), Result(scalar=project), Result(row=(45.5, 2))])
        with patch.object(project_service, "SessionLocal", return_value=session):
            result = await project_service.get_project_card(100, 2)
        self.assertEqual(result, (project, 45.5, 2))
        self.assertIn('Transaction.type == "expense"', inspect.getsource(project_service.get_project_card))

    async def test_project_view_does_not_touch_activity(self):
        session = Session([Result(scalar=7), Result(scalar=SimpleNamespace(id=2))])
        with patch.object(project_service, "SessionLocal", return_value=session), \
             patch.object(project_service, "touch_family_activity", AsyncMock()) as touch:
            await project_service.get_project(100, 2)
        touch.assert_not_awaited()


class QuickInputTests(unittest.IsolatedAsyncioTestCase):
    async def test_plain_input_keeps_null_project(self):
        transaction = SimpleNamespace(project_id=None)
        user = SimpleNamespace(id=1, family_id=7)
        with patch.object(expense_service, "get_user_by_telegram_id", AsyncMock(return_value=user)), \
             patch.object(expense_service, "create_transaction", AsyncMock(return_value=transaction)) as create:
            result = await expense_service.save_transaction("кофе 20", 100, 7)
        self.assertIs(result, transaction)
        self.assertIsNone(create.await_args.kwargs["project_id"])

    async def test_known_tag_assigns_project_and_is_removed_from_title(self):
        project = SimpleNamespace(id=5, is_active=True, name="Ремонт квартиры", tag="ремонт")
        transaction = SimpleNamespace(project_id=5)
        user = SimpleNamespace(id=1, family_id=7)
        with patch.object(expense_service, "get_user_by_telegram_id", AsyncMock(return_value=user)), \
             patch.object(expense_service, "find_family_project_by_tag", AsyncMock(return_value=project)) as find, \
             patch.object(expense_service, "create_transaction", AsyncMock(return_value=transaction)) as create:
            result = await expense_service.save_transaction("кофе 20 #Дача", 100, 7)
        self.assertIs(result, transaction)
        find.assert_awaited_once_with(7, "дача")
        self.assertEqual(create.await_args.kwargs["title"].casefold(), "кофе")
        self.assertEqual(create.await_args.kwargs["project_id"], 5)
        self.assertEqual(result.project_name, "Ремонт квартиры")

    async def test_unknown_tag_does_not_create_transaction_and_suggests(self):
        suggestion = SimpleNamespace(id=5, tag="дача", name="Дача")
        user = SimpleNamespace(id=1, family_id=7)
        with patch.object(expense_service, "get_user_by_telegram_id", AsyncMock(return_value=user)), \
             patch.object(expense_service, "find_family_project_by_tag", AsyncMock(return_value=None)), \
             patch.object(expense_service, "suggest_active_family_project", AsyncMock(return_value=suggestion)), \
             patch.object(expense_service, "create_transaction", AsyncMock()) as create:
            result = await expense_service.save_transaction("краска 45 #дачп", 100, 7)
        self.assertIsInstance(result, expense_service.PendingProjectTransaction)
        self.assertEqual(result.status, "not_found")
        self.assertIs(result.suggestion, suggestion)
        create.assert_not_awaited()

    async def test_inactive_project_does_not_create_transaction(self):
        project = SimpleNamespace(id=5, is_active=False)
        user = SimpleNamespace(id=1, family_id=7)
        with patch.object(expense_service, "get_user_by_telegram_id", AsyncMock(return_value=user)), \
             patch.object(expense_service, "find_family_project_by_tag", AsyncMock(return_value=project)), \
             patch.object(expense_service, "create_transaction", AsyncMock()) as create:
            result = await expense_service.save_transaction("краска 45 #дача", 100, 7)
        self.assertEqual(result.status, "inactive")
        create.assert_not_awaited()

    async def test_transaction_cannot_use_project_from_another_family(self):
        session = Session([Result(scalar=None)])
        with patch.object(expense_service, "SessionLocal", return_value=session), \
             patch.object(expense_service, "touch_family_activity", AsyncMock()) as touch:
            with self.assertRaises(ValueError):
                await expense_service.create_transaction(
                    user_id=1, family_id=7, title="Краска", amount=45,
                    transaction_type="expense", project_id=99,
                )
        self.assertEqual(session.added, [])
        touch.assert_not_awaited()


class ProjectHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def _save_confirmation(self, transaction):
        message, state = Message("шпаклевка 40") , State()
        user = SimpleNamespace(id=1, family_id=7)
        with patch.object(expenses, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=7))), \
             patch.object(expenses, "get_user_by_telegram_id", AsyncMock(return_value=user)), \
             patch.object(expenses, "save_transaction", AsyncMock(return_value=transaction)):
            await expenses.add_transaction(message, state)
        return message.answers[-1][0]

    async def test_confirmation_without_project_is_unchanged(self):
        transaction = SimpleNamespace(
            id=1, type="expense", amount=40.0, category="📦 Прочее",
            title="шпаклевка", project_id=None,
        )
        text = await self._save_confirmation(transaction)
        self.assertNotIn("🏷 Проект:", text)
        self.assertIn("✅ Сохранено операций: 1", text)

    async def test_confirmation_shows_escaped_project_name_only(self):
        transaction = SimpleNamespace(
            id=1, type="expense", amount=40.0, category="📦 Прочее",
            title="шпаклевка", project_id=5, project_name="Ремонт <A&B>",
        )
        text = await self._save_confirmation(transaction)
        self.assertIn("🏷 Проект: Ремонт &lt;A&amp;B&gt;", text)
        self.assertNotIn("#ремонт", text)
        self.assertNotIn("project_id", text)
        self.assertNotIn("family_id", text)

    async def test_missing_project_object_does_not_break_confirmation(self):
        transaction = SimpleNamespace(
            id=1, type="expense", amount=40.0, category="📦 Прочее",
            title="шпаклевка", project_id=999,
        )
        text = await self._save_confirmation(transaction)
        self.assertNotIn("🏷 Проект:", text)

    async def test_project_creation_fsm_and_duplicate_tag(self):
        message, state = Message(" Дача "), State()
        await projects.project_name(message, state)
        self.assertEqual(state.value, ProjectState.waiting_for_tag)
        self.assertEqual(state.data["project_name"], "Дача")

        message.text = "#Дача"
        with patch.object(projects, "create_project", AsyncMock(side_effect=project_service.DuplicateProjectTagError)):
            await projects.project_tag(message, state)
        self.assertFalse(state.cleared)
        self.assertIn("уже используется", message.answers[-1][0])

    async def test_project_callback_contains_no_family_id(self):
        packed = ProjectCallback(action="card", project_id=5).pack()
        self.assertNotIn("family", packed)

    async def test_cancel_pending_operation_creates_nothing_and_clears_state(self):
        callback, state = Callback(), State({
            "pending_project_family_id": 7,
            "pending_project_chat_id": 500,
            "pending_project_parsed": {"title": "Краска", "amount": 45.0,
                                       "type": "expense", "category": "📦 Прочее"},
        })
        user = SimpleNamespace(id=1, family_id=7)
        with patch.object(expenses, "get_user_by_telegram_id", AsyncMock(return_value=user)), \
             patch.object(expenses, "create_transaction", AsyncMock()) as create:
            await expenses.resolve_pending_project_transaction(
                callback,
                SimpleNamespace(action="cancel", project_id=0),
                state,
            )
        create.assert_not_awaited()
        self.assertTrue(state.cleared)

    async def test_without_project_creates_null_project_and_clears_state(self):
        callback, state = Callback(), State({
            "pending_project_family_id": 7,
            "pending_project_chat_id": 500,
            "pending_project_parsed": {"title": "Краска", "amount": 45.0,
                                       "type": "expense", "category": "📦 Прочее"},
        })
        user = SimpleNamespace(id=1, family_id=7)
        transaction = SimpleNamespace(type="expense", title="Краска", amount=45.0)
        with patch.object(expenses, "get_user_by_telegram_id", AsyncMock(return_value=user)), \
             patch.object(expenses, "create_transaction", AsyncMock(return_value=transaction)) as create:
            await expenses.resolve_pending_project_transaction(
                callback, SimpleNamespace(action="without", project_id=0), state,
            )
        self.assertIsNone(create.await_args.kwargs["project_id"])
        self.assertTrue(state.cleared)

    async def test_select_suggestion_creates_project_transaction(self):
        callback, state = Callback(), State({
            "pending_project_family_id": 7,
            "pending_project_chat_id": 500,
            "pending_project_parsed": {"title": "Краска", "amount": 45.0,
                                       "type": "expense", "category": "📦 Прочее"},
        })
        user = SimpleNamespace(id=1, family_id=7)
        project = SimpleNamespace(id=5, family_id=7, is_active=True)
        transaction = SimpleNamespace(type="expense", title="Краска", amount=45.0)
        with patch.object(expenses, "get_user_by_telegram_id", AsyncMock(return_value=user)), \
             patch.object(expenses, "get_project", AsyncMock(return_value=project)), \
             patch.object(expenses, "create_transaction", AsyncMock(return_value=transaction)) as create:
            await expenses.resolve_pending_project_transaction(
                callback, SimpleNamespace(action="select", project_id=5), state,
            )
        self.assertEqual(create.await_args.kwargs["project_id"], 5)
        self.assertTrue(state.cleared)

    async def test_foreign_suggested_project_cannot_be_selected(self):
        callback, state = Callback(), State({
            "pending_project_family_id": 7,
            "pending_project_chat_id": 500,
            "pending_project_parsed": {"title": "Краска", "amount": 45.0,
                                       "type": "expense", "category": "📦 Прочее"},
        })
        user = SimpleNamespace(id=1, family_id=7)
        with patch.object(expenses, "get_user_by_telegram_id", AsyncMock(return_value=user)), \
             patch.object(expenses, "get_project", AsyncMock(return_value=None)), \
             patch.object(expenses, "create_transaction", AsyncMock()) as create:
            await expenses.resolve_pending_project_transaction(
                callback, SimpleNamespace(action="select", project_id=99), state,
            )
        create.assert_not_awaited()
        self.assertTrue(state.cleared)

    def test_project_transaction_state_prevents_general_expense_handler(self):
        self.assertIn("@router.message(StateFilter(None))", inspect.getsource(expenses.add_transaction))
        self.assertIsNotNone(ProjectTransactionState.waiting_for_resolution)
