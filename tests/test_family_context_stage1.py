import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import BigInteger

from app.database.models import Family
from app.handlers import start
from app.handlers.user_states import RegistrationState
from app.services import family_context_service


class FamilyContextStageOneTests(unittest.TestCase):
    def test_family_has_nullable_unique_bigint_chat_id(self):
        column = Family.__table__.c.telegram_chat_id
        self.assertIsInstance(column.type, BigInteger)
        self.assertTrue(column.nullable)
        self.assertTrue(column.unique)

    def test_service_uses_chat_scope_and_rolls_back_integrity_error(self):
        source = inspect.getsource(family_context_service)
        self.assertIn("Family.telegram_chat_id == chat_id", source)
        self.assertIn("len(legacy_families) != 1", source)
        self.assertIn("await session.rollback()", source)


class StartContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_stores_current_chat_family_for_registration(self):
        message = SimpleNamespace(
            text="/start",
            chat=SimpleNamespace(id=-100123, title="Group A"),
            from_user=SimpleNamespace(id=7, full_name="Ann"),
            answer=AsyncMock(),
        )
        state = SimpleNamespace(
            set_state=AsyncMock(), update_data=AsyncMock(), clear=AsyncMock()
        )
        with patch.object(start, "get_or_create_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=4))), \
             patch.object(start, "get_user_by_telegram_id", AsyncMock(return_value=None)):
            await start.cmd_start(message, state)

        state.set_state.assert_awaited_once_with(RegistrationState.waiting_for_name)
        state.update_data.assert_awaited_once_with(registration_family_id=4)
