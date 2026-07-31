import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers import menu, statistics
from app.keyboards.main_menu import back_to_main_menu_keyboard, main_menu


class _Message:
    def __init__(self):
        self.from_user = SimpleNamespace(id=1)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


class MonthButtonTests(unittest.IsolatedAsyncioTestCase):
    def test_menu_filter_matches_main_keyboard_text(self):
        source = inspect.getsource(menu)
        self.assertIn('F.text == "📅 Месяц"', source)
        self.assertIn("StateFilter(None)", source)

    async def test_month_menu_delegates_to_month_handler(self):
        message = _Message()
        with patch.object(menu, "month", AsyncMock()) as month:
            await menu.month_menu(message)
        month.assert_awaited_once_with(message)

    async def test_month_response_keeps_inline_and_compact_back_keyboard(self):
        message = _Message()
        user = SimpleNamespace(family_id=3)
        data = {
            "ordinary_income": 110.0, "ordinary_expense": 89.02,
            "recurring_income": 3875.0, "recurring_expense": 1877.36,
            "recurring_income_count": 5, "recurring_expense_count": 16,
            "balance": 2018.62, "transactions": [], "total": 0,
        }
        with patch.object(statistics, "get_user_by_telegram_id", AsyncMock(return_value=user)), \
             patch.object(statistics, "get_month_statistics", AsyncMock(return_value=data)):
            await statistics.month(message)

        report, report_kwargs = message.answers[0]
        _, keyboard_kwargs = message.answers[1]
        self.assertIn("Регулярные расходы", report)
        self.assertNotEqual(report, "Главное меню")
        self.assertNotEqual(report_kwargs["reply_markup"], main_menu)
        self.assertTrue(report_kwargs["reply_markup"].inline_keyboard)
        self.assertEqual(keyboard_kwargs["reply_markup"], back_to_main_menu_keyboard)

    def test_month_callbacks_preserve_year_month_and_page(self):
        keyboard = statistics.month_keyboard(2026, 7, 20, 50)
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
        self.assertIn("month:2026:06", callbacks)
        self.assertIn("month:2026:08", callbacks)
        self.assertIn("month:2026:07:40", callbacks)
