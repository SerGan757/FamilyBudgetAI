import unittest
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy.dialects import postgresql

from app.handlers import statistics
from app.handlers.history import format_transaction as history_format
from app.handlers.statistics import format_month, format_today, format_transaction
from app.services.financial_feed_service import DisplayOperation, _feed_query


def goal_row(amount=500, created_at=None):
    return DisplayOperation(
        kind="goal_contribution", id=15,
        created_at=created_at or datetime(2026, 8, 9, 12), amount=amount,
        title="Машина <A>", user_name="Вася", type="goal_contribution",
    )


def base_data(rows=None, goal=500):
    return {
        "income": 2000.0, "expense": 1000.0, "balance": 1000.0,
        "ordinary_income": 2000.0, "ordinary_expense": 1000.0,
        "recurring_income": 0.0, "recurring_expense": 0.0,
        "recurring_income_count": 0, "recurring_expense_count": 0,
        "transactions": rows or [], "total": len(rows or []),
        "goal_contributions": goal,
    }


class GoalDisplayFeedTests(unittest.TestCase):
    def test_union_feed_is_family_scoped_before_sort_and_pagination(self):
        sql = str(_feed_query(7).select().compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
        )).lower()
        self.assertIn("union all", sql)
        self.assertGreaterEqual(sql.count("family_id = 7"), 3)
        self.assertIn("goal_contributions", sql)
        self.assertIn("transactions", sql)

    def test_goal_has_numeric_identifier_and_html_safe_display(self):
        row = goal_row()
        for text in (history_format(row, "PLN", "pl"), format_transaction(row, "PLN", "pl")):
            self.assertIn("15 🎯", text)
            self.assertNotIn("G15", text)
            self.assertNotIn("🎯15", text)
            self.assertIn("+500.00 zł", text)
            self.assertIn("Машина &lt;A&gt;", text)

    def test_today_and_month_show_goal_separately_without_changing_totals(self):
        data = base_data([goal_row()])
        today = format_today(data, date(2026, 8, 9), currency_code="EUR", language="en")
        month = format_month(data, 2026, 8, currency_code="EUR", language="en")
        for text in (today, month):
            self.assertIn("To goal", text)
            self.assertIn("500.00 €", text)
            self.assertIn("Income", text)
            self.assertIn("2 000.00 €", text)
            self.assertIn("Expense", text)
            self.assertIn("1 000.00 €", text)
            self.assertIn("15 🎯", text)
            self.assertIn("Free balance", text)


class GoalBalanceHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_balance_keeps_accounting_balance_and_adds_free_balance(self):
        message = SimpleNamespace(
            chat=SimpleNamespace(id=1, type="private"), from_user=SimpleNamespace(id=2),
            answer=AsyncMock(),
        )
        family = SimpleNamespace(id=7, currency="EUR", language="en", temporary_screen_ttl=0)
        data = {
            "ordinary_income": 2000.0, "ordinary_expense": 1000.0,
            "recurring_income": 0.0, "recurring_expense": 0.0,
            "recurring_income_count": 0, "recurring_expense_count": 0,
            "balance": 1000.0, "goal_contributions": 500.0, "free_balance": 500.0,
        }
        with patch.object(statistics, "require_family_for_chat", AsyncMock(return_value=family)), \
             patch.object(statistics, "get_balance", AsyncMock(return_value=data)):
            await statistics.balance(message)
        text = message.answer.await_args.args[0]
        self.assertIn("Remaining: 1 000.00 €", text)
        self.assertIn("Reserved for goal: 500.00 €", text)
        self.assertIn("Free balance: 500.00 €", text)


if __name__ == "__main__":
    unittest.main()
