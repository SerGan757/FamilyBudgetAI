import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.keyboards.recurring_inline import delete_keyboard
from app.services import recurring_manager, recurring_service


class _Result:
    def __init__(self, value): self.value = value
    def scalar_one_or_none(self): return self.value


class _Session:
    def __init__(self, payment): self.payment, self.queries, self.deleted = payment, [], []
    async def __aenter__(self): return self
    async def __aexit__(self, *_): return None
    async def execute(self, query):
        self.queries.append(str(query))
        return _Result(self.payment) if len(self.queries) == 1 else _Result(None)
    async def delete(self, value): self.deleted.append(value)
    async def commit(self): pass


class RecurringDeleteTests(unittest.IsolatedAsyncioTestCase):
    def test_callback_matches_handler_prefix(self):
        self.assertEqual(delete_keyboard(12).inline_keyboard[0][0].callback_data, "rec_delete:12")

    async def test_own_template_deletes_only_current_regular_transaction(self):
        payment, session = SimpleNamespace(id=12, family_id=3), None
        session = _Session(payment)
        with patch.object(recurring_service, "SessionLocal", return_value=session):
            self.assertTrue(await recurring_service.delete_payment(12, 3))
        self.assertEqual(session.deleted, [payment])
        delete_sql = session.queries[1]
        self.assertIn("recurring_period", delete_sql)
        self.assertIn("is_recurring", delete_sql)

    async def test_other_family_template_is_not_deleted(self):
        session = _Session(None)
        with patch.object(recurring_service, "SessionLocal", return_value=session):
            self.assertFalse(await recurring_service.delete_payment(12, 3))
        self.assertEqual(session.deleted, [])
        self.assertEqual(len(session.queries), 1)

    async def test_manager_passes_explicit_family(self):
        with patch.object(recurring_manager, "delete_payment", AsyncMock(return_value=True)) as delete:
            self.assertTrue(await recurring_manager.remove_payment(3, 12))
        delete.assert_awaited_once_with(12, 3)
