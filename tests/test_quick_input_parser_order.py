import unittest

from app.services.parser import parse_message
from app.services.project_service import extract_project_tag


class QuickInputParserOrderTests(unittest.TestCase):
    def assert_parsed(self, text, transaction_type, amount, title):
        parsed = parse_message(text)
        self.assertIsNotNone(parsed, text)
        self.assertEqual(parsed["type"], transaction_type)
        self.assertAlmostEqual(parsed["amount"], amount)
        self.assertEqual(parsed["title"], title)

    def test_expense_amount_can_be_first_or_last(self):
        cases = (
            ("7.22 пицца", 7.22, "пицца"),
            ("пицца 7.22", 7.22, "пицца"),
            ("7,22 продукты", 7.22, "продукты"),
            ("продукты 7,22", 7.22, "продукты"),
            ("5 кофе", 5, "кофе"),
            ("кофе 5", 5, "кофе"),
            ("Lidl 42.80", 42.8, "Lidl"),
            ("42.80 Lidl", 42.8, "Lidl"),
        )
        for text, amount, title in cases:
            with self.subTest(text=text):
                self.assert_parsed(text, "expense", amount, title)

    def test_income_amount_can_be_first_or_last(self):
        for text, amount, title in (
            ("+2000 зарплата", 2000, "зарплата"),
            ("зарплата +2000", 2000, "зарплата"),
            ("+250 премия", 250, "премия"),
            ("премия +250", 250, "премия"),
            ("+ зарплата 2000", 2000, "зарплата"),
        ):
            with self.subTest(text=text):
                self.assert_parsed(text, "income", amount, title)

    def test_goal_contribution_keeps_priority(self):
        for text in ("++500", "++ 500", "++500 машина"):
            with self.subTest(text=text):
                parsed = parse_message(text)
                self.assertEqual(parsed["type"], "goal_contribution")
                self.assertEqual(parsed["amount"], 500)

    def test_project_tag_is_removed_before_either_order_is_parsed(self):
        for text in ("40 краска #ремонт", "краска 40 #ремонт"):
            with self.subTest(text=text):
                transaction_text, tag = extract_project_tag(text)
                self.assertEqual(tag, "ремонт")
                self.assert_parsed(transaction_text, "expense", 40, "краска")

    def test_income_with_project_tag(self):
        transaction_text, tag = extract_project_tag("+500 подработка #проект")
        self.assertEqual(tag, "проект")
        self.assert_parsed(transaction_text, "income", 500, "подработка")

    def test_existing_currency_text_and_decimal_comma(self):
        for text in ("7.22 €", "7.22 евро", "7,22"):
            with self.subTest(text=text):
                parsed = parse_message(text)
                self.assertEqual(parsed["type"], "expense")
                self.assertAlmostEqual(parsed["amount"], 7.22)

    def test_multiple_amounts_are_rejected(self):
        self.assertIsNone(parse_message("10 пицца 20"))


if __name__ == "__main__":
    unittest.main()
