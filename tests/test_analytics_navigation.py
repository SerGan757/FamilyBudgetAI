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
        chat=SimpleNamespace(id=100, type="private"),
        answer=AsyncMock(),
        edit_text=AsyncMock(),
    )
    return SimpleNamespace(
        data=data, message=message, from_user=SimpleNamespace(id=1),
        answer=AsyncMock(),
    )


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
        self.assertIn("📅 До конца месяца: 0 дней (100%)", text)
        self.assertIn("📈 Прогноз расходов: 40.00 €", text)
        keyboard = event.message.edit_text.await_args.kwargs["reply_markup"]
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
        self.assertEqual(callbacks, [
            "analytics:2026:06", "analytics:2026:08", "analytics_help:2026:07",
        ])

    async def test_next_month_edits_existing_message(self):
        event = await self._navigate("analytics:2026:09")
        event.message.edit_text.assert_awaited_once()
        event.message.answer.assert_not_awaited()
        event.answer.assert_awaited_once_with()
        text = event.message.edit_text.await_args.args[0]
        self.assertIn("📅 До конца месяца: 30 дней (0%)", text)
        self.assertNotIn("📈 Прогноз расходов:", text)
        self.assertIn("🏷 <b>Проекты</b>", text)

    async def test_help_edits_message_and_back_preserves_selected_month(self):
        event = callback("analytics_help:2026:07")
        with patch.object(
            statistics, "require_family_for_chat",
            AsyncMock(return_value=SimpleNamespace(id=7)),
        ):
            await statistics.analytics_help(event)
        event.message.edit_text.assert_awaited_once()
        event.message.answer.assert_not_awaited()
        self.assertIn("📊 <b>Как читать прогноз</b>", event.message.edit_text.await_args.args[0])
        back_markup = event.message.edit_text.await_args.kwargs["reply_markup"]
        self.assertEqual(
            back_markup.inline_keyboard[0][0].callback_data,
            "analytics_back:2026:07",
        )
        event.answer.assert_awaited_once_with()

        back = callback("analytics_back:2026:07")
        with patch.object(
            statistics, "require_family_for_chat",
            AsyncMock(return_value=SimpleNamespace(id=7)),
        ), patch.object(
            statistics, "get_analytics", AsyncMock(return_value=analytics_data()),
        ) as get_analytics:
            await statistics.analytics_back(back)
        get_analytics.assert_awaited_once_with(7, 2026, 7)
        text = back.message.edit_text.await_args.args[0]
        self.assertIn("Аналитика • Июль 2026", text)
        callbacks = [
            button.callback_data
            for row in back.message.edit_text.await_args.kwargs["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertEqual(callbacks, [
            "analytics:2026:06", "analytics:2026:08", "analytics_help:2026:07",
        ])
        back.message.answer.assert_not_awaited()
        back.answer.assert_awaited_once_with()

    async def test_forecast_labels_for_deficit_balance_and_pace(self):
        cases = (
            (
                SimpleNamespace(
                    days_remaining=23, elapsed_percent=26, spent_percent=64,
                    forecast_expenses=4797.56, forecast_balance=-651.56,
                    pace_delta=4,
                ),
                ("🔴 Прогноз дефицита: 651.56 €", "⚠️ Превышение темпа расходов: 4%"),
            ),
            (
                SimpleNamespace(
                    days_remaining=23, elapsed_percent=26, spent_percent=20,
                    forecast_expenses=500.0, forecast_balance=500.0,
                    pace_delta=-12,
                ),
                ("🟢 Прогноз остатка: 500.00 €", "✅ Темп расходов ниже плана: 12%"),
            ),
            (
                SimpleNamespace(
                    days_remaining=23, elapsed_percent=26, spent_percent=26,
                    forecast_expenses=740.0, forecast_balance=260.0,
                    pace_delta=0,
                ),
                ("🟢 Прогноз остатка: 260.00 €", "✅ Темп расходов: по плану"),
            ),
        )
        for forecast, expected in cases:
            with self.subTest(pace_delta=forecast.pace_delta):
                message = callback("unused").message
                with patch.object(
                    statistics, "get_analytics", AsyncMock(return_value=analytics_data()),
                ), patch.object(
                    statistics, "calculate_analytics_forecast", return_value=forecast,
                ):
                    await statistics.analytics(
                        message, 2026, 8, family_id=7, edit_existing=True,
                    )
                text = message.edit_text.await_args.args[0]
                self.assertIn("📅 До конца месяца: 23 дня (26%)", text)
                self.assertIn(expected[0], text)
                self.assertIn(expected[1], text)
                self.assertNotIn("Прогноз дефицита: -", text)

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
