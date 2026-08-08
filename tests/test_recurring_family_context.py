import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers import recurring
from app.services import recurring_manager, recurring_service


class _Result:
    def __init__(self, one=None, many=None):
        self.one = one
        self.many = many or []

    def scalar_one_or_none(self):
        return self.one

    def scalars(self):
        return self

    def all(self):
        return self.many


class _Session:
    def __init__(self, results):
        self.results = iter(results)
        self.queries = []
        self.deleted = []
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self): return self
    async def __aexit__(self, *_): return None
    async def execute(self, query):
        self.queries.append(str(query))
        return next(self.results)
    async def delete(self, value): self.deleted.append(value)
    def add(self, value): self.added.append(value)
    async def commit(self): self.commits += 1
    async def rollback(self): self.rollbacks += 1


class _State:
    def __init__(self, data): self.data, self.cleared = data, False
    async def get_data(self): return self.data
    async def get_state(self): return "recurring"
    async def clear(self): self.cleared = True


def _message(chat_id, text):
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id, type="group"),
        from_user=SimpleNamespace(id=500),
        text=text,
        answer=AsyncMock(),
    )


class RecurringFamilyContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_families_list_only_their_templates(self):
        templates_a = [SimpleNamespace(id=1, family_id=10)]
        templates_b = [SimpleNamespace(id=2, family_id=20)]
        with patch.object(
            recurring_manager, "get_payments", AsyncMock(side_effect=[templates_a, templates_b])
        ) as get_payments:
            self.assertEqual(await recurring_manager.list_payments(10), templates_a)
            self.assertEqual(await recurring_manager.list_payments(20), templates_b)
        self.assertEqual(get_payments.await_args_list[0].args, (10,))
        self.assertEqual(get_payments.await_args_list[1].args, (20,))

    async def test_create_template_uses_explicit_family(self):
        parsed = {"title": "Salary", "amount": 1500.0, "type": "income", "category": "income"}
        with patch.object(recurring_manager, "parse_message", return_value=parsed), patch.object(
            recurring_manager, "add_payment", AsyncMock(return_value=SimpleNamespace(family_id=10))
        ) as add_payment:
            payment = await recurring_manager.create_payment(10, "Salary +1500")
        self.assertEqual(payment.family_id, 10)
        self.assertEqual(add_payment.await_args.kwargs["family_id"], 10)

    async def test_other_family_cannot_update_or_delete_template(self):
        with patch.object(recurring_manager, "update_payment_in_db", AsyncMock(return_value=None)) as update, patch.object(
            recurring_manager, "delete_payment", AsyncMock(return_value=False)
        ) as delete:
            self.assertIsNone(await recurring_manager.update_payment(20, 1, "Rent 100"))
            self.assertFalse(await recurring_manager.remove_payment(20, 1))
        self.assertEqual(update.await_args.kwargs["family_id"], 20)
        delete.assert_awaited_once_with(1, 20)

    async def test_generation_sets_family_and_is_idempotent(self):
        payment = SimpleNamespace(id=1, title="Salary", amount=1500.0, type="income", category="income")
        first_session = _Session([_Result(one=None)])
        with patch.object(recurring_manager, "get_payments", AsyncMock(return_value=[payment])), patch.object(
            recurring_manager, "SessionLocal", return_value=first_session
        ):
            result = await recurring_manager.create_month_transactions(10, 500, date(2026, 8, 20))
        self.assertEqual(result["created"], 1)
        self.assertEqual(first_session.added[0].family_id, 10)
        self.assertEqual(first_session.added[0].user_id, 500)
        self.assertEqual(first_session.added[0].recurring_period, date(2026, 8, 1))
        self.assertEqual(first_session.commits, 1)
        self.assertIn("transactions.family_id", first_session.queries[0])

        existing = SimpleNamespace(title="Salary", amount=1500.0, type="income", category="income")
        second_session = _Session([_Result(one=existing)])
        with patch.object(recurring_manager, "get_payments", AsyncMock(return_value=[payment])), patch.object(
            recurring_manager, "SessionLocal", return_value=second_session
        ):
            result = await recurring_manager.create_month_transactions(10, 500, date(2026, 8, 20))
        self.assertEqual(result["unchanged"], 1)
        self.assertEqual(second_session.added, [])

    async def test_generation_for_family_b_uses_family_b(self):
        payment = SimpleNamespace(id=2, title="Rent", amount=100.0, type="expense", category="other")
        session = _Session([_Result(one=None)])
        with patch.object(recurring_manager, "get_payments", AsyncMock(return_value=[payment])), patch.object(
            recurring_manager, "SessionLocal", return_value=session
        ):
            await recurring_manager.create_month_transactions(20, 501, date(2026, 8, 20))
        self.assertEqual(session.added[0].family_id, 20)

    async def test_create_month_maps_telegram_id_to_internal_family_user_id(self):
        message = _message(100, "📅 Создать операции месяца")
        message.from_user.id = 274540057
        state = _State({})
        user = SimpleNamespace(id=1, telegram_id=274540057, family_id=10)
        result = {"created": 0, "updated": 0, "unchanged": 0, "details": []}
        with patch.object(
            recurring, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=10)),
        ), patch.object(
            recurring, "get_user_by_telegram_id", AsyncMock(return_value=user),
        ) as get_user, patch.object(
            recurring, "create_month_transactions", AsyncMock(return_value=result),
        ) as create:
            await recurring.create_month(message, state)
        get_user.assert_awaited_once_with(274540057)
        create.assert_awaited_once_with(10, 1)
        self.assertNotEqual(create.await_args.args[1], 274540057)

    async def test_unknown_or_other_family_user_creates_nothing(self):
        for user in (None, SimpleNamespace(id=1, family_id=20)):
            message = _message(100, "📅 Создать операции месяца")
            state = _State({})
            with patch.object(
                recurring, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=10)),
            ), patch.object(
                recurring, "get_user_by_telegram_id", AsyncMock(return_value=user),
            ), patch.object(recurring, "create_month_transactions", AsyncMock()) as create:
                await recurring.create_month(message, state)
            create.assert_not_awaited()
            self.assertIn("не зарегистрирован", message.answer.await_args.args[0])

    async def test_income_and_expense_templates_commit_atomically(self):
        payments = [
            SimpleNamespace(id=1, title="Salary", amount=1500.0, type="income", category="income"),
            SimpleNamespace(id=2, title="Rent", amount=700.0, type="expense", category="home"),
        ]
        session = _Session([_Result(one=None), _Result(one=None)])
        with patch.object(recurring_manager, "get_payments", AsyncMock(return_value=payments)), \
             patch.object(recurring_manager, "SessionLocal", return_value=session):
            result = await recurring_manager.create_month_transactions(10, 1, date(2026, 8, 20))
        self.assertEqual(result["created"], 2)
        self.assertEqual([item.type for item in session.added], ["income", "expense"])
        self.assertEqual([item.user_id for item in session.added], [1, 1])
        self.assertEqual([item.recurring_period for item in session.added], [date(2026, 8, 1)] * 2)
        self.assertEqual(session.commits, 1)

    async def test_generation_error_rolls_back_whole_month(self):
        payments = [
            SimpleNamespace(id=1, title="Salary", amount=1500.0, type="income", category="income"),
            SimpleNamespace(id=2, title="Rent", amount=700.0, type="expense", category="home"),
        ]
        session = _Session([_Result(one=None)])
        original_execute = session.execute

        async def execute_then_fail(query):
            if session.queries:
                raise RuntimeError("simulated second-template failure")
            return await original_execute(query)

        session.execute = execute_then_fail
        with patch.object(recurring_manager, "get_payments", AsyncMock(return_value=payments)), \
             patch.object(recurring_manager, "SessionLocal", return_value=session):
            with self.assertRaises(RuntimeError):
                await recurring_manager.create_month_transactions(10, 1, date(2026, 8, 20))
        self.assertEqual(session.commits, 0)
        self.assertEqual(session.rollbacks, 1)

    async def test_month_transactions_are_scoped_to_family(self):
        session = _Session([_Result(many=[SimpleNamespace(family_id=10)])])
        with patch.object(recurring_manager, "SessionLocal", return_value=session):
            rows = await recurring_manager.get_month_recurring_transactions(10, date(2026, 8, 20))
        self.assertEqual([row.family_id for row in rows], [10])
        self.assertIn("transactions.family_id", session.queries[0])

    async def test_delete_scopes_current_month_transaction_to_family(self):
        payment = SimpleNamespace(id=1, family_id=10)
        session = _Session([_Result(one=payment), _Result(), _Result()])
        with patch.object(recurring_service, "SessionLocal", return_value=session):
            self.assertTrue(await recurring_service.delete_payment(1, 10))
        self.assertIn("transactions.family_id", session.queries[1])
        self.assertIn("recurring_period", session.queries[1])
        self.assertIn("is_recurring", session.queries[1])

    async def test_fsm_cannot_continue_in_another_chat(self):
        state = _State({"recurring_family_id": 10, "recurring_chat_id": 100})
        message = _message(200, "Rent 100")
        with patch.object(
            recurring, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=20))
        ), patch.object(recurring, "create_payment", AsyncMock()) as create:
            await recurring.save_template(message, state)
        self.assertTrue(state.cleared)
        create.assert_not_awaited()
        self.assertIn("другом чате", message.answer.await_args.args[0])

    async def test_fsm_clears_after_success_and_uses_saved_family(self):
        state = _State({"recurring_family_id": 10, "recurring_chat_id": 100})
        message = _message(100, "Rent 100")
        payment = SimpleNamespace(title="Rent", amount=100.0)
        with patch.object(
            recurring, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=10))
        ), patch.object(recurring, "create_payment", AsyncMock(return_value=payment)) as create:
            await recurring.save_template(message, state)
        self.assertTrue(state.cleared)
        create.assert_awaited_once_with(10, "Rent 100")

    async def test_callback_from_family_b_cannot_delete_family_a_template(self):
        callback = SimpleNamespace(
            data="rec_delete:1",
            from_user=SimpleNamespace(id=500),
            message=SimpleNamespace(chat=SimpleNamespace(id=200, type="group"), edit_text=AsyncMock()),
            answer=AsyncMock(),
        )
        with patch.object(
            recurring, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=20))
        ), patch.object(recurring, "remove_payment", AsyncMock(return_value=False)) as remove:
            await recurring.delete_template_callback(callback)
        remove.assert_awaited_once_with(20, 1)
        callback.message.edit_text.assert_not_awaited()
