import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import BigInteger

from app.database.models import User
from app.handlers import registration, start
from app.handlers.user_states import RegistrationState
from app.services import user_service


TELEGRAM_ID = 6332185543


class _Session:
    def __init__(self, result=None):
        self.result = result
        self.added = None

    async def __aenter__(self): return self
    async def __aexit__(self, *_): return None
    async def execute(self, _query): return self.result
    def add(self, value): self.added = value
    async def commit(self): pass
    async def refresh(self, _value): pass


class _Result:
    def __init__(self, value): self.value = value
    def scalar_one_or_none(self): return self.value


class _State:
    def __init__(self, data=None):
        self.data = data or {}
        self.cleared = False
        self.set_state = AsyncMock()
        self.update_data = AsyncMock(side_effect=self.data.update)

    async def get_data(self): return self.data
    async def clear(self): self.cleared = True


class TelegramIdBigintTests(unittest.IsolatedAsyncioTestCase):
    def test_user_telegram_id_column_is_bigint(self):
        self.assertIsInstance(User.__table__.c.telegram_id.type, BigInteger)

    async def test_create_and_lookup_accept_big_telegram_id(self):
        created_session = _Session()
        with patch.object(user_service, "SessionLocal", return_value=created_session):
            created = await user_service.create_user(TELEGRAM_ID, "Ann", 10)
        self.assertEqual(created.telegram_id, TELEGRAM_ID)

        found = SimpleNamespace(telegram_id=TELEGRAM_ID)
        with patch.object(user_service, "SessionLocal", return_value=_Session(_Result(found))):
            self.assertIs(await user_service.get_user_by_telegram_id(TELEGRAM_ID), found)

    async def test_start_and_registration_keep_big_telegram_id(self):
        message = SimpleNamespace(
            text="/start",
            chat=SimpleNamespace(id=100, title="Family"),
            from_user=SimpleNamespace(id=TELEGRAM_ID, full_name="Ann"),
            answer=AsyncMock(),
        )
        state = _State()
        family = SimpleNamespace(id=10)
        with patch.object(start, "get_or_create_family_for_chat", AsyncMock(return_value=family)), \
             patch.object(start, "get_user_by_telegram_id", AsyncMock(return_value=None)):
            await start.cmd_start(message, state)
        state.set_state.assert_awaited_once_with(RegistrationState.waiting_for_name)
        self.assertEqual(state.update_data.await_args.kwargs["registration_family_id"], 10)

        name_message = SimpleNamespace(
            text="Ann",
            chat=SimpleNamespace(id=100),
            from_user=SimpleNamespace(id=TELEGRAM_ID),
            answer=AsyncMock(),
        )
        registration_state = _State({
            "registration_family_id": 10,
            "registration_chat_id": 100,
            "pending_operation_text": "Coffee 5",
        })
        transaction = SimpleNamespace(type="expense", amount=5.0, category="Food", title="Coffee")
        with patch.object(registration, "require_family_for_chat", AsyncMock(return_value=family)), \
             patch.object(registration, "create_user", AsyncMock()) as create_user, \
             patch.object(registration, "save_transaction", AsyncMock(return_value=transaction)) as save:
            await registration.finish_group_registration(name_message, registration_state)
        create_user.assert_awaited_once_with(telegram_id=TELEGRAM_ID, name="Ann", family_id=10)
        save.assert_awaited_once_with("Coffee 5", TELEGRAM_ID, 10)
        self.assertTrue(registration_state.cleared)
