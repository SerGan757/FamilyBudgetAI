import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers import menu, statistics
from app.keyboards.main_menu import main_menu


class _Message:
    def __init__(self):
        self.from_user = SimpleNamespace(id=1)
        self.chat = SimpleNamespace(id=100)
        self.answers = []
        self.bot = SimpleNamespace(edit_message_reply_markup=AsyncMock())
        self.sent = SimpleNamespace(chat=SimpleNamespace(id=100), message_id=55)

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))
        return self.sent


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
        family = SimpleNamespace(id=3)
        data = {
            "ordinary_income": 110.0, "ordinary_expense": 89.02,
            "recurring_income": 3875.0, "recurring_expense": 1877.36,
            "recurring_income_count": 5, "recurring_expense_count": 16,
            "balance": 2018.62, "transactions": [], "total": 0,
        }
        with patch.object(statistics, "require_family_for_chat", AsyncMock(return_value=family)) as require_family, \
             patch.object(statistics, "get_month_statistics", AsyncMock(return_value=data)) as get_month:
            await statistics.month(message)

        self.assertEqual(len(message.answers), 1)
        report, report_kwargs = message.answers[0]
        self.assertIn("Регулярные расходы", report)
        self.assertNotEqual(report, "Главное меню")
        inline = report_kwargs["reply_markup"]
        self.assertTrue(inline.inline_keyboard)
        callbacks = [button.callback_data for row in inline.inline_keyboard for button in row]
        self.assertTrue(callbacks)
        self.assertTrue(all(callbacks))
        message.bot.edit_message_reply_markup.assert_not_awaited()
        require_family.assert_awaited_once_with(100)
        self.assertEqual(get_month.await_args.args[0], 3)

    def test_month_callbacks_preserve_year_month_and_page(self):
        keyboard = statistics.month_keyboard(2026, 7, 20, 50)
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
        self.assertIn("month:2026:06", callbacks)
        self.assertIn("month:2026:08", callbacks)
        self.assertIn("month:2026:07:40", callbacks)
