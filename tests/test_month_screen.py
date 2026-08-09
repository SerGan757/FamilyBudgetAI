import unittest
from types import SimpleNamespace

from app.handlers.statistics import _shift_month, format_month, month_keyboard
from app.services.statistics_service import build_balance_data


class MonthScreenTests(unittest.TestCase):
    def test_july_breakdown_has_no_double_counting(self):
        rows = [SimpleNamespace(type="income", is_recurring=False, amount=110),
                SimpleNamespace(type="expense", is_recurring=False, amount=89.02)]
        rows += [SimpleNamespace(type="income", is_recurring=True, amount=775)] * 5
        rows += [SimpleNamespace(type="expense", is_recurring=True, amount=117.335)] * 16
        data = build_balance_data(rows)
        self.assertAlmostEqual(data["balance"], 2018.62, places=2)
        self.assertEqual(data["recurring_income_count"], 5)
        self.assertEqual(data["recurring_expense_count"], 16)

    def test_empty_month_and_year_boundaries(self):
        data = build_balance_data([]) | {"transactions": [], "total": 0}
        self.assertIn("Операций за этот месяц нет", format_month(data, 2026, 8))
        self.assertEqual(_shift_month(2026, 1, -1), (2025, 12))
        self.assertEqual(_shift_month(2026, 12, 1), (2027, 1))

    def test_navigation_and_pagination_keep_selected_month(self):
        keyboard = month_keyboard(2026, 7, 20, 41)
        data = [button.callback_data for row in keyboard.inline_keyboard for button in row]
        self.assertIn("month:2026:06", data)
        self.assertIn("month:2026:08", data)
        self.assertIn("month:2026:07:0", data)

    def test_month_title_uses_the_shared_i18n_month_formatter(self):
        data = build_balance_data([]) | {"transactions": [], "total": 0}
        expected = {
            "de": "September 2026",
            "en": "September 2026",
            "ru": "Сентябрь 2026",
            "uk": "Вересень 2026",
            "pl": "Wrzesień 2026",
            "cs": "Září 2026",
            "hu": "Szeptember 2026",
        }
        for language, title in expected.items():
            with self.subTest(language=language):
                self.assertIn(title, format_month(data, 2026, 9, language=language))

    def test_month_navigation_keeps_locale_across_year_boundary(self):
        data = build_balance_data([]) | {"transactions": [], "total": 0}
        next_year, next_month = _shift_month(2026, 12, 1)
        self.assertIn("Januar 2027", format_month(data, next_year, next_month, language="de"))
        keyboard = month_keyboard(2026, 12, 0, 0, "de")
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
        self.assertIn("month:2027:01", callbacks)
