import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers import expenses, recurring
from app.services import family_context_service
from app.services.family_context_service import FamilyContextNotFoundError


class State:
    async def set_state(self, value):
        self.value = value

    async def update_data(self, **values):
        self.data = values


def private_message(text="кофе 5", telegram_id=123456789):
    return SimpleNamespace(
        text=text,
        chat=SimpleNamespace(id=telegram_id, type="private", title=None),
        from_user=SimpleNamespace(id=telegram_id, full_name="Test User"),
        answer=AsyncMock(),
    )


class PrivateFamilyContextServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_registered_user_uses_user_family_not_chat_binding(self):
        family = SimpleNamespace(id=3, telegram_chat_id=-100500)
        with patch.object(
            family_context_service, "get_family_by_user_telegram_id",
            AsyncMock(return_value=family),
        ) as by_user, patch.object(
            family_context_service, "get_family_by_chat_id", AsyncMock(),
        ) as by_chat:
            result = await family_context_service.require_family_for_chat(
                123456789, chat_type="private", telegram_id=123456789,
            )
        self.assertIs(result, family)
        by_user.assert_awaited_once_with(123456789)
        by_chat.assert_not_awaited()
        self.assertNotEqual(123456789, family.telegram_chat_id)

    async def test_group_and_supergroup_use_only_bound_chat(self):
        for chat_type in ("group", "supergroup"):
            family = SimpleNamespace(id=3)
            with self.subTest(chat_type=chat_type), patch.object(
                family_context_service, "get_family_by_chat_id",
                AsyncMock(return_value=family),
            ) as by_chat, patch.object(
                family_context_service, "get_family_by_user_telegram_id", AsyncMock(),
            ) as by_user:
                result = await family_context_service.require_family_for_chat(
                    -100500, chat_type=chat_type, telegram_id=123456789,
                )
            self.assertIs(result, family)
            by_chat.assert_awaited_once_with(-100500)
            by_user.assert_not_awaited()

    async def test_unknown_private_user_has_no_context(self):
        with patch.object(
            family_context_service, "get_family_by_user_telegram_id",
            AsyncMock(return_value=None),
        ):
            with self.assertRaises(FamilyContextNotFoundError):
                await family_context_service.require_family_for_chat(
                    999, chat_type="private", telegram_id=999,
                )


class PrivateFamilyContextHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_expense_is_saved_in_registered_users_family(self):
        message = private_message()
        family = SimpleNamespace(id=3)
        user = SimpleNamespace(id=7, telegram_id=123456789, family_id=3)
        transaction = SimpleNamespace(
            type="expense", amount=5.0, category="☕ Еда", title="кофе",
        )
        with patch.object(
            family_context_service, "get_family_by_user_telegram_id",
            AsyncMock(return_value=family),
        ), patch.object(
            expenses, "get_user_by_telegram_id", AsyncMock(return_value=user),
        ), patch.object(
            expenses, "save_transaction", AsyncMock(return_value=transaction),
        ) as save:
            await expenses.add_transaction(message, State())
        save.assert_awaited_once_with("кофе 5", 123456789, 3)

    async def test_unknown_private_user_gets_safe_message_and_creates_nothing(self):
        message = private_message(telegram_id=999)
        with patch.object(
            family_context_service, "get_family_by_user_telegram_id",
            AsyncMock(return_value=None),
        ), patch.object(expenses, "save_transaction", AsyncMock()) as save:
            await expenses.add_transaction(message, State())
        save.assert_not_awaited()
        self.assertIn("ещё не подключены", message.answer.await_args.args[0])
        self.assertIn("/start", message.answer.await_args.args[0])

    async def test_private_recurring_month_uses_internal_user_and_family(self):
        message = private_message("📅 Создать операции месяца")
        state = SimpleNamespace(
            get_data=AsyncMock(return_value={}), get_state=AsyncMock(return_value=None),
            clear=AsyncMock(),
        )
        user = SimpleNamespace(id=7, telegram_id=123456789, family_id=3)
        result = {"created": 0, "updated": 0, "unchanged": 0, "details": []}
        with patch.object(
            recurring, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=3)),
        ) as context, patch.object(
            recurring, "get_user_by_telegram_id", AsyncMock(return_value=user),
        ), patch.object(
            recurring, "create_month_transactions", AsyncMock(return_value=result),
        ) as create:
            await recurring.create_month(message, state)
        context.assert_awaited_once_with(
            123456789, chat_type="private", telegram_id=123456789,
        )
        create.assert_awaited_once_with(3, 7)


if __name__ == "__main__":
    unittest.main()
