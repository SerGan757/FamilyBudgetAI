import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers import expenses, history, projects, recurring, statistics
from app.utils.currency import (
    CURRENCY_SYMBOLS, currency_symbol, format_money, normalize_currency_code,
)


class CurrencyCatalogTests(unittest.TestCase):
    def test_all_supported_currency_symbols(self):
        expected = {
            "EUR": "€", "USD": "$", "UAH": "₴", "GBP": "£",
            "PLN": "zł", "CZK": "Kč", "RON": "lei", "CHF": "CHF",
            "HUF": "Ft", "SEK": "kr", "NOK": "kr", "DKK": "kr",
        }
        self.assertEqual(CURRENCY_SYMBOLS, expected)
        for code, symbol in expected.items():
            self.assertEqual(currency_symbol(code), symbol)
            self.assertEqual(format_money(20, code), f"20.00 {symbol}")

    def test_unknown_null_and_empty_currency_fall_back_to_eur(self):
        for value in (None, "", "BTC"):
            self.assertEqual(normalize_currency_code(value), "EUR")
            self.assertEqual(format_money(20, value), "20.00 €")

    def test_switch_changes_only_display_not_amount(self):
        self.assertEqual(format_money(100, "EUR"), "100.00 €")
        self.assertEqual(format_money(100, "PLN"), "100.00 zł")


def transaction(transaction_type="expense", amount=20.0):
    return SimpleNamespace(
        id=1, type=transaction_type, amount=amount, category="🛒 Продукты",
        title="кофе", is_recurring=False, user_name="Вася",
        user=SimpleNamespace(name="Вася"), project_name=None,
    )


def month_data():
    return {
        "income": 100.0, "expense": 20.0,
        "ordinary_income": 100.0, "ordinary_expense": 20.0,
        "recurring_income": 30.0, "recurring_expense": 10.0,
        "recurring_income_count": 1, "recurring_expense_count": 1,
        "balance": 100.0, "transactions": [transaction()], "total": 1,
    }


def analytics_data():
    return {
        **month_data(), "operations": 1, "average_check": 20.0,
        "average_day": 2.0, "users": [("Вася", 20.0)],
        "categories": [("Продукты", 20.0)], "biggest": None,
        "projects": [("Ремонт", 20.0)],
    }


class ReportFormatterCurrencyTests(unittest.IsolatedAsyncioTestCase):
    def test_history_today_and_month_use_selected_currency(self):
        item = transaction()
        self.assertIn("20.00 zł", history.format_transaction(item, "PLN"))
        today = statistics.format_today(month_data(), date(2026, 8, 8), currency_code="UAH")
        month = statistics.format_month(month_data(), 2026, 8, currency_code="GBP")
        self.assertIn("20.00 ₴", today)
        self.assertNotIn("€", today)
        self.assertIn("20.00 £", month)
        self.assertIn("10.00 £/мес", month)
        self.assertNotIn("€", month)

    async def test_balance_uses_family_currency(self):
        sent = SimpleNamespace(
            bot=SimpleNamespace(), chat=SimpleNamespace(id=1), message_id=2,
        )
        message = SimpleNamespace(
            chat=SimpleNamespace(id=1, type="private"), from_user=SimpleNamespace(id=2),
            answer=AsyncMock(return_value=sent),
        )
        family = SimpleNamespace(id=7, currency="USD", temporary_screen_ttl=0)
        with patch.object(statistics, "require_family_for_chat", AsyncMock(return_value=family)), \
             patch.object(statistics, "get_balance", AsyncMock(return_value=month_data())):
            await statistics.balance(message)
        text = message.answer.await_args.args[0]
        self.assertIn("100.00 $", text)
        self.assertIn("10.00 $/мес", text)
        self.assertNotIn("€", text)

    async def test_analytics_projects_and_forecast_use_selected_currency(self):
        sent = SimpleNamespace(bot=SimpleNamespace(), chat=SimpleNamespace(id=1), message_id=2)
        message = SimpleNamespace(
            chat=SimpleNamespace(id=1), from_user=SimpleNamespace(id=2),
            answer=AsyncMock(return_value=sent),
            bot=SimpleNamespace(edit_message_reply_markup=AsyncMock()),
        )
        with patch.object(statistics, "get_analytics", AsyncMock(return_value=analytics_data())):
            await statistics.analytics(
                message, 2026, 8, family_id=7, currency_code="CZK",
                temporary_screen_ttl=0,
            )
        text = message.answer.await_args.args[0]
        self.assertIn("20.00 Kč", text)
        self.assertIn("Прогноз расходов:", text)
        self.assertIn("Kč", text.split("Прогноз расходов:", 1)[1])
        self.assertIn("Проекты", text)
        self.assertNotIn("€", text)


class UserFlowCurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def _quick_confirmation(self, transaction_type):
        saved = transaction(transaction_type)
        family = SimpleNamespace(id=7, currency="PLN")
        user = SimpleNamespace(id=3, family_id=7)
        message = SimpleNamespace(
            text="+20 зарплата" if transaction_type == "income" else "кофе 20",
            chat=SimpleNamespace(id=10, type="private", title=None),
            from_user=SimpleNamespace(id=5, full_name="Вася"), answer=AsyncMock(),
        )
        state = SimpleNamespace(update_data=AsyncMock(), set_state=AsyncMock())
        with patch.object(expenses, "require_family_for_chat", AsyncMock(return_value=family)), \
             patch.object(expenses, "get_user_by_telegram_id", AsyncMock(return_value=user)), \
             patch.object(expenses, "save_transaction", AsyncMock(return_value=saved)):
            await expenses.add_transaction(message, state)
        return message.answer.await_args.args[0]

    async def test_quick_expense_and_income_confirmation_use_family_currency(self):
        expense_text = await self._quick_confirmation("expense")
        income_text = await self._quick_confirmation("income")
        self.assertIn("-20.00 zł", expense_text)
        self.assertIn("Расходы: 20.00 zł", expense_text)
        self.assertIn("+20.00 zł", income_text)
        self.assertIn("Доходы: 20.00 zł", income_text)
        self.assertNotIn("€", expense_text + income_text)

    async def test_recurring_and_project_card_use_family_currency(self):
        family = SimpleNamespace(id=7, currency="RON")
        payment = SimpleNamespace(type="expense", amount=50.0, title="Интернет")
        message = SimpleNamespace(
            chat=SimpleNamespace(id=10, type="private"), from_user=SimpleNamespace(id=5),
            answer=AsyncMock(),
        )
        state = SimpleNamespace(
            clear=AsyncMock(), update_data=AsyncMock(), set_state=AsyncMock(),
            get_state=AsyncMock(return_value=None),
        )
        with patch.object(recurring, "require_family_for_chat", AsyncMock(return_value=family)), \
             patch.object(recurring, "list_payments", AsyncMock(return_value=[payment])):
            await recurring.add_template(message, state)
        text = message.answer.await_args.args[0]
        self.assertIn("50.00 lei/мес", text)
        project = SimpleNamespace(name="Ремонт", tag="ремонт", is_active=True)
        card = projects.project_card_text(project, 100.0, 1, "CHF")
        self.assertIn("100.00 CHF", card)


if __name__ == "__main__":
    unittest.main()
