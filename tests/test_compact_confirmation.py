import unittest
from types import SimpleNamespace

from app.handlers.expenses import quick_confirmation_text


def transaction(operation_id, operation_type, amount, title="Pizza", project_name=None):
    return SimpleNamespace(
        id=operation_id,
        type=operation_type,
        amount=amount,
        title=title,
        category="📦 Other",
        project_name=project_name,
    )


class CompactConfirmationTests(unittest.TestCase):
    def test_expense_only_has_expense_total_without_income_or_separators(self):
        text = quick_confirmation_text([transaction(1, "expense", 80)], "en", "UAH")
        self.assertIn("Expenses: 80.00 ₴", text)
        self.assertNotIn("Income:", text)
        self.assertNotIn("===", text)
        self.assertNotIn("──", text)
        self.assertNotIn("<pre", text)
        self.assertNotIn("<code", text)
        self.assertEqual(len(text.splitlines()), 3)

    def test_income_only_has_income_total_without_expenses(self):
        text = quick_confirmation_text([transaction(2, "income", 2000, "Salary")], "en", "UAH")
        self.assertIn("Income: 2 000.00 ₴", text)
        self.assertNotIn("Expenses:", text)
        self.assertIn("+2 000.00 ₴", text)

    def test_mixed_batch_has_both_totals(self):
        text = quick_confirmation_text([
            transaction(1, "income", 500), transaction(2, "expense", 120),
        ], "en", "EUR")
        self.assertIn("Income: 500.00 €", text)
        self.assertIn("Expenses: 120.00 €", text)

    def test_expense_only_batch_omits_income(self):
        text = quick_confirmation_text([
            transaction(1, "expense", 40), transaction(2, "expense", 80),
        ], "en", "EUR")
        self.assertNotIn("Income:", text)
        self.assertIn("Expenses: 120.00 €", text)

    def test_income_only_batch_omits_expenses(self):
        text = quick_confirmation_text([
            transaction(1, "income", 40), transaction(2, "income", 80),
        ], "en", "EUR")
        self.assertNotIn("Expenses:", text)
        self.assertIn("Income: 120.00 €", text)

    def test_project_expense_keeps_project_and_escapes_user_text(self):
        text = quick_confirmation_text([
            transaction(1, "expense", 40, "Paint <x>", "Home & Garden"),
        ], "en", "EUR")
        self.assertIn("📁 Project: Home &amp; Garden", text)
        self.assertIn("Paint &lt;x&gt;", text)
        self.assertNotIn("Income:", text)

    def test_amount_order_does_not_affect_confirmation_formatter(self):
        first = quick_confirmation_text([transaction(1, "expense", 7.22, "pizza")], "en", "EUR")
        last = quick_confirmation_text([transaction(2, "expense", 7.22, "pizza")], "en", "EUR")
        self.assertEqual(first, last)


if __name__ == "__main__":
    unittest.main()
