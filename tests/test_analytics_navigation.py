import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramBadRequest

from app.handlers import statistics


def analytics_data():
    return {
        "ordinary_income": 100.0,
        "ordinary_expense": 40.0,
        "recurring_income": 0.0,
        "recurring_expense": 0.0,
        "recurring_income_count": 0,
        "recurring_expense_count": 0,
        "balance": 60.0,
        "operations": 1,
        "average_check": 40.0,
        "average_day": 40.0,
        "users": [],
        "categories": [],
        "biggest": None,
        "projects": [("Ремонт", 40.0)],
    }


def callback(data: str):
    message = SimpleNamespace(
        chat=SimpleNamespace(id=100),
        answer=AsyncMock(),
        edit_text=AsyncMock(),
    )
    return SimpleNamespace(data=data, message=message, answer=AsyncMock())


class AnalyticsNavigationTests(unittest.IsolatedAsyncioTestCase):
    async def _navigate(self, data: str):
        event = callback(data)
        with patch.object(
            statistics, "require_family_for_chat",
            AsyncMock(return_value=SimpleNamespace(id=7)),
        ), patch.object(
            statistics, "get_analytics", AsyncMock(return_value=analytics_data()),
        ):
            await statistics.analytics_page(event)
        return event

    async def test_previous_month_edits_existing_message(self):
        event = await self._navigate("analytics:2026:07")
        event.message.edit_text.assert_awaited_once()
        event.message.answer.assert_not_awaited()
        event.answer.assert_awaited_once_with()

        text = event.message.edit_text.await_args.args[0]
        self.assertIn("📊 <b>Аналитика • Июль 2026</b>", text)
        self.assertIn("🏷 <b>Проекты</b>", text)
        self.assertIn("📅 До конца месяца: 0 дней", text)
        self.assertIn("⏳ Прошло месяца: 100%", text)
        self.assertIn("📈 Прогноз расходов: 40.00 €", text)
        keyboard = event.message.edit_text.await_args.kwargs["reply_markup"]
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
        self.assertEqual(callbacks, ["analytics:2026:06", "analytics:2026:08"])

    async def test_next_month_edits_existing_message(self):
        event = await self._navigate("analytics:2026:09")
        event.message.edit_text.assert_awaited_once()
        event.message.answer.assert_not_awaited()
        event.answer.assert_awaited_once_with()
        text = event.message.edit_text.await_args.args[0]
        self.assertIn("📅 До конца месяца: 30 дней", text)
        self.assertIn("⏳ Прошло месяца: 0%", text)
        self.assertNotIn("📈 Прогноз расходов:", text)
        self.assertIn("🏷 <b>Проекты</b>", text)

    async def test_message_not_modified_is_safe_and_callback_is_answered(self):
        event = callback("analytics:2026:08")
        event.message.edit_text.side_effect = TelegramBadRequest(
            method=SimpleNamespace(), message="Bad Request: message is not modified",
        )
        with patch.object(
            statistics, "require_family_for_chat",
            AsyncMock(return_value=SimpleNamespace(id=7)),
        ), patch.object(
            statistics, "get_analytics", AsyncMock(return_value=analytics_data()),
        ):
            await statistics.analytics_page(event)
        event.message.answer.assert_not_awaited()
        event.answer.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
