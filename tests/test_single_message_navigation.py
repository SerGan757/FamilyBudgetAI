import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers import history, statistics
from app.keyboards.main_menu import back_to_main_menu_keyboard


class Message:
    def __init__(self):
        self.chat = SimpleNamespace(id=100, type="private")
        self.from_user = SimpleNamespace(id=1)
        self.answer = AsyncMock()
        self.bot = SimpleNamespace(edit_message_reply_markup=AsyncMock())
        self.sent = SimpleNamespace(chat=SimpleNamespace(id=100), message_id=55)
        self.answer.return_value = self.sent


def month_data():
    return {
        "income": 0.0, "expense": 0.0,
        "ordinary_income": 0.0, "ordinary_expense": 0.0,
        "recurring_income": 0.0, "recurring_expense": 0.0,
        "recurring_income_count": 0, "recurring_expense_count": 0,
        "balance": 0.0, "transactions": [], "total": 0,
    }


def analytics_data():
    return {
        "ordinary_income": 0.0, "ordinary_expense": 40.0,
        "recurring_income": 0.0, "recurring_expense": 0.0,
        "recurring_income_count": 0, "recurring_expense_count": 0,
        "balance": -40.0, "operations": 1, "average_check": 40.0,
        "average_day": 40.0, "users": [], "categories": [], "biggest": None,
        "projects": [("Ремонт", 40.0)],
    }


class SingleMessageNavigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_balance_remains_one_useful_message_with_back_keyboard(self):
        message = Message()
        with patch.object(
            statistics, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=1)),
        ), patch.object(statistics, "get_balance", AsyncMock(return_value=month_data())):
            await statistics.balance(message)
        message.answer.assert_awaited_once()
        self.assertIs(message.answer.await_args.kwargs["reply_markup"], back_to_main_menu_keyboard)
        message.bot.edit_message_reply_markup.assert_not_awaited()

    async def test_history_sends_one_useful_message_and_keeps_both_keyboards(self):
        message = Message()
        with patch.object(
            history, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=1)),
        ), patch.object(history, "get_transactions_count", AsyncMock(return_value=25)), \
             patch.object(history, "build_history_text", AsyncMock(return_value="📋 История пуста.")):
            await history.history(message)
        self._assert_one_message_with_navigation(message, "История")

    async def test_today_sends_one_useful_message_and_keeps_both_keyboards(self):
        message = Message()
        with patch.object(
            statistics, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=1)),
        ), patch.object(statistics, "get_today_statistics", AsyncMock(return_value=month_data())):
            await statistics.today(message)
        self._assert_one_message_with_navigation(message, "Доходы")

    async def test_month_sends_one_useful_message_and_keeps_both_keyboards(self):
        message = Message()
        with patch.object(
            statistics, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=1)),
        ), patch.object(statistics, "get_month_statistics", AsyncMock(return_value=month_data())):
            await statistics.month(message)
        self._assert_one_message_with_navigation(message, "месяц")

    async def test_analytics_sends_one_useful_message_and_keeps_projects(self):
        message = Message()
        with patch.object(
            statistics, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=1)),
        ), patch.object(statistics, "get_analytics", AsyncMock(return_value=analytics_data())):
            await statistics.analytics(message, 2026, 8)
        self._assert_one_message_with_navigation(message, "Аналитика")
        self.assertIn("🏷 <b>Проекты</b>", message.answer.await_args.args[0])

    def _assert_one_message_with_navigation(self, message, expected_text):
        message.answer.assert_awaited_once()
        self.assertIn(expected_text, message.answer.await_args.args[0])
        self.assertNotIn("\u2063", message.answer.await_args.args[0])
        inline = message.answer.await_args.kwargs["reply_markup"]
        self.assertTrue(inline.inline_keyboard)
        callbacks = [
            button.callback_data
            for row in inline.inline_keyboard
            for button in row
        ]
        self.assertTrue(callbacks)
        self.assertTrue(all(callbacks))
        message.bot.edit_message_reply_markup.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
