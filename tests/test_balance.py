import unittest
from types import SimpleNamespace

from app.services.statistics_service import build_balance_data


class BalanceTests(unittest.TestCase):
    def test_monthly_balance_splits_regular_and_ordinary_without_double_counting(self):
        rows = [
            SimpleNamespace(type="income", is_recurring=False, amount=60.00),
            SimpleNamespace(type="expense", is_recurring=False, amount=69.02),
            *[SimpleNamespace(type="income", is_recurring=True, amount=775.00)] * 5,
            *[SimpleNamespace(type="expense", is_recurring=True, amount=117.335)] * 16,
        ]
        data = build_balance_data(rows)
        self.assertEqual(data["ordinary_income"], 60.00)
        self.assertEqual(data["ordinary_expense"], 69.02)
        self.assertEqual(data["recurring_income"], 3875.00)
        self.assertAlmostEqual(data["recurring_expense"], 1877.36, places=2)
        self.assertEqual(data["recurring_income_count"], 5)
        self.assertEqual(data["recurring_expense_count"], 16)
        self.assertAlmostEqual(data["balance"], 1988.62, places=2)
