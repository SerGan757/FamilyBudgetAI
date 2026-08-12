import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers import expenses, registration
from app.handlers.user_states import RegistrationState


class _State:
    def __init__(self, data=None):
        self.data = data or {}
        self.current_state = None
        self.cleared = False

    async def set_state(self, state):
        self.current_state = state

    async def update_data(self, **kwargs):
        self.data.update(kwargs)

    async def get_data(self):
        return self.data

    async def clear(self):
        self.cleared = True


class _Message:
    def __init__(self, text, telegram_id):
        self.text = text
        self.from_user = SimpleNamespace(id=telegram_id, full_name="Test User")
        self.chat = SimpleNamespace(id=telegram_id, type="private", title=None)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


class RegistrationFlowTests(unittest.IsolatedAsyncioTestCase):
    def test_expenses_handler_has_empty_state_filter(self):
        self.assertIn("@router.message(StateFilter(None))", inspect.getsource(expenses))

    async def test_new_user_operation_stays_in_fsm_without_transaction(self):
        message, state = _Message("Кофе 5", 101), _State()
        family = SimpleNamespace(id=10)
        with patch.object(expenses, "get_user_by_telegram_id", AsyncMock(return_value=None)), \
             patch.object(expenses, "require_family_for_chat", AsyncMock(return_value=family)), \
             patch.object(expenses, "get_or_create_family_for_chat", AsyncMock(return_value=family)), \
             patch.object(expenses, "save_transaction", AsyncMock()) as save:
            await expenses.add_transaction(message, state)

        self.assertEqual(state.current_state, RegistrationState.waiting_for_group_name)
        self.assertEqual(state.data["pending_operation_text"], "Кофе 5")
        self.assertEqual(state.data["registration_family_id"], 10)
        self.assertEqual(state.data["registration_chat_id"], 101)
        save.assert_not_awaited()

    async def test_registered_user_operation_is_saved_once(self):
        message, state = _Message("Кофе 5", 101), _State()
        user = SimpleNamespace(id=1, family_id=1)
        transaction = SimpleNamespace(id=174, type="expense", amount=5.0, category="☕ Еда", title="Кофе")
        with patch.object(expenses, "get_user_by_telegram_id", AsyncMock(return_value=user)), \
             patch.object(expenses, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=1))), \
             patch.object(expenses, "save_transaction", AsyncMock(return_value=transaction)) as save:
            await expenses.add_transaction(message, state)

        save.assert_awaited_once_with("Кофе 5", 101, 1)

    async def test_registration_creates_user_and_pending_transaction_once(self):
        message = _Message("Аня", 101)
        state = _State({"pending_operation_text": "Кофе 5", "registration_family_id": 10, "registration_chat_id": 101})
        transaction = SimpleNamespace(type="expense", amount=5.0, category="☕ Еда", title="Кофе")
        with patch.object(registration, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=10))), \
             patch.object(registration, "create_user", AsyncMock()) as create_user, \
             patch.object(registration, "save_transaction", AsyncMock(return_value=transaction)) as save:
            await registration.finish_group_registration(message, state)

        create_user.assert_awaited_once_with(telegram_id=101, name="Аня", family_id=10)
        save.assert_awaited_once_with("Кофе 5", 101, 10)
        self.assertTrue(state.cleared)

    async def test_name_is_never_sent_to_expense_service(self):
        message = _Message("Аня", 101)
        state = _State({"pending_operation_text": "Кофе 5", "registration_family_id": 10, "registration_chat_id": 101})
        transaction = SimpleNamespace(type="expense", amount=5.0, category="☕ Еда", title="Кофе")
        with patch.object(registration, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=10))), \
             patch.object(registration, "create_user", AsyncMock()), \
             patch.object(registration, "save_transaction", AsyncMock(return_value=transaction)) as save:
            await registration.finish_group_registration(message, state)

        self.assertEqual([call.args[0] for call in save.await_args_list], ["Кофе 5"])

    async def test_no_pending_operation_does_not_create_transaction(self):
        message, state = _Message("Аня", 101), _State({"registration_family_id": 10, "registration_chat_id": 101})
        with patch.object(registration, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=10))), \
             patch.object(registration, "create_user", AsyncMock()) as create_user, \
             patch.object(registration, "save_transaction", AsyncMock()) as save:
            await registration.finish_group_registration(message, state)

        create_user.assert_awaited_once()
        save.assert_not_awaited()

    async def test_completed_registration_name_is_not_an_operation(self):
        message, state = _Message("Аня", 101), _State()
        user = SimpleNamespace(id=1, family_id=1)
        with patch.object(expenses, "get_user_by_telegram_id", AsyncMock(return_value=user)), \
             patch.object(expenses, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=1))), \
             patch.object(expenses, "save_transaction", AsyncMock(return_value="PARSE_ERROR")) as save:
            await expenses.add_transaction(message, state)

        save.assert_awaited_once_with("Аня", 101, 1)

    async def test_two_new_users_keep_independent_pending_operations(self):
        first, second = _State(), _State()
        family = SimpleNamespace(id=10)
        with patch.object(expenses, "get_user_by_telegram_id", AsyncMock(return_value=None)), \
             patch.object(expenses, "require_family_for_chat", AsyncMock(return_value=family)), \
             patch.object(expenses, "get_or_create_family_for_chat", AsyncMock(return_value=family)):
            await expenses.add_transaction(_Message("Кофе 5", 101), first)
            await expenses.add_transaction(_Message("Хлеб 3", 202), second)

        self.assertEqual(first.data["pending_operation_text"], "Кофе 5")
        self.assertEqual(second.data["pending_operation_text"], "Хлеб 3")

    async def test_registration_started_in_another_chat_creates_nothing(self):
        message = _Message("Аня", 202)
        state = _State({
            "pending_operation_text": "Кофе 5",
            "registration_family_id": 10,
            "registration_chat_id": 101,
        })
        with patch.object(registration, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=20))), \
             patch.object(registration, "create_user", AsyncMock()) as create_user, \
             patch.object(registration, "save_transaction", AsyncMock()) as save:
            await registration.finish_group_registration(message, state)

        self.assertTrue(state.cleared)
        create_user.assert_not_awaited()
        save.assert_not_awaited()
        self.assertIn("другом чате", message.answers[0][0])

    async def test_membership_mismatch_does_not_create_transaction_or_user(self):
        message, state = _Message("Кофе 5", 101), _State()
        user = SimpleNamespace(id=1, family_id=20)
        with patch.object(expenses, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=10))), \
             patch.object(expenses, "get_user_by_telegram_id", AsyncMock(return_value=user)), \
             patch.object(expenses, "save_transaction", AsyncMock()) as save, \
             patch.object(expenses, "get_or_create_family_for_chat", AsyncMock()) as create_family:
            await expenses.add_transaction(message, state)

        save.assert_not_awaited()
        create_family.assert_not_awaited()
        self.assertIsNone(state.current_state)
        self.assertIn("другой семье", message.answers[0][0])
