import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers.history import format_transaction as history_format
from app.handlers.statistics import format_transaction as statistics_format
from app.services import delete_service, history_service, recurring_manager, statistics_service
from app.services.parser import parse_message


class _Result:
    def scalar_one_or_none(self):
        return None


class _Session:
    async def execute(self, _query):
        return _Result()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class SafeStageTests(unittest.IsolatedAsyncioTestCase):
    def test_regular_income_parser(self):
        parsed = parse_message("Зарплата +2300")
        self.assertEqual(parsed["type"], "income")

    async def test_generator_creates_typed_regular_transaction(self):
        user = SimpleNamespace(id=7, family_id=3)
        payment = SimpleNamespace(id=11, title="Salary", amount=2300.0, type="income", category="💰 Доход")
        with patch.object(recurring_manager, "get_user_by_telegram_id", AsyncMock(return_value=user)), \
             patch.object(recurring_manager, "get_payments", AsyncMock(return_value=[payment])), \
             patch("app.database.db.SessionLocal", return_value=_Session()), \
             patch("app.services.expense_service.create_transaction", AsyncMock()) as create:
            result = await recurring_manager.create_month_transactions(1)
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["details"][0]["type"], "income")
        self.assertTrue(create.await_args.kwargs["is_recurring"])
        self.assertEqual(create.await_args.kwargs["transaction_type"], "income")

    def test_html_is_escaped_in_history(self):
        row = SimpleNamespace(id=1, type="expense", amount=1.0, is_recurring=True,
                              title="A < B & C", category="🛒 Food", user_name="<Bob>")
        text = history_format(row)
        self.assertIn("A &lt; B &amp; C", text)
        self.assertIn("🔁", text)
        self.assertIn("/мес", text)

    def test_today_month_format_regular_rows(self):
        row = SimpleNamespace(id=1, type="income", amount=10.0, is_recurring=True,
                              title="Income", category="💰 Income", user=SimpleNamespace(name="Ann"))
        self.assertIn("🔁 💰", statistics_format(row))
        self.assertIn("/мес", statistics_format(row))

    def test_family_scope_is_required_by_services(self):
        self.assertIn("family_id", inspect.signature(history_service.get_last_transactions).parameters)
        self.assertIn("family_id", inspect.signature(statistics_service.get_today_statistics).parameters)
        self.assertIn("family_id", inspect.signature(delete_service.delete_transaction_by_id).parameters)
