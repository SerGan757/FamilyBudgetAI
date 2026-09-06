import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy.dialects import postgresql

from app.services import statistics_service
from app.services.year_analytics_service import year_expense_categories_statement


def transaction(kind, amount, category, title, *, recurring=False):
    return SimpleNamespace(
        type=kind, amount=amount, category=category, title=title,
        custom_category=None, is_recurring=recurring,
        created_at=datetime(2026, 9, 1), user=SimpleNamespace(name="User"),
    )


class ExpenseCategoryAnalyticsTests(unittest.IsolatedAsyncioTestCase):
    async def analytics(self, transactions, goal=None):
        stats = {
            "ordinary_income":0, "ordinary_expense":0,
            "recurring_income":0, "recurring_expense":0, "balance":0,
        }
        with patch.object(statistics_service,"get_month_statistics",AsyncMock(return_value=stats)), \
             patch.object(statistics_service,"get_month_transactions",AsyncMock(return_value=transactions)), \
             patch.object(statistics_service,"get_project_expense_statistics",AsyncMock(return_value=[])), \
             patch("app.services.savings_goal_service.get_goal_snapshot",AsyncMock(return_value=goal)):
            return await statistics_service.get_analytics(7,2026,9,include_goal=True)

    async def test_income_and_recurring_income_never_enter_expense_categories(self):
        rows = [
            transaction("income",1150,"💰 Доход","Зарплата"),
            transaction("income",300,"💰 Доход","Пособие",recurring=True),
            transaction("expense",270.9,"🛒 Продукты","Продукты"),
        ]
        result=await self.analytics(rows)
        self.assertEqual(result["categories"],[('🛒 Продукты',270.9)])

    async def test_mixed_expenses_are_ranked_by_expense_totals_only(self):
        rows = [
            transaction("income",1150,"💰 Доход","Зарплата"),
            transaction("expense",1150,"🏠 Дом","Аренда"),
            transaction("expense",100,"🐾 Животные","Ветеринар"),
            transaction("expense",20,"🏠 Дом","Вода"),
        ]
        result=await self.analytics(rows,goal=SimpleNamespace(month_saved=500))
        self.assertEqual(result["categories"],[('🏠 Дом',1170),('🐾 Животные',100)])

    async def test_mislabeled_expense_is_reclassified_not_hidden(self):
        rent=transaction("expense",1150,"💰 Доход","Аренда")
        result=await self.analytics([rent])
        self.assertNotIn(("💰 Доход",1150),result["categories"])
        self.assertEqual(result["categories"],[('🏠 Дом',1150)])
        self.assertIs(result["biggest"],rent)

    def test_year_category_query_aggregates_only_expense_type(self):
        statement=year_expense_categories_statement(
            7,datetime(2026,1,1),datetime(2027,1,1),
        )
        sql=str(statement.compile(
            dialect=postgresql.dialect(),compile_kwargs={"literal_binds":True},
        ))
        self.assertIn("transactions.type = 'expense'",sql)
        self.assertNotIn("transactions.type = 'income' THEN transactions.amount",sql)
