import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy.dialects import postgresql

from app.handlers import statistics
from app.services import statistics_service


class Result:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class Session:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, statement):
        self.statement = statement
        return Result(self.rows)


class Message:
    def __init__(self):
        self.chat = SimpleNamespace(id=100)
        self.answers = []
        self.bot = SimpleNamespace(edit_message_reply_markup=AsyncMock())
        self.sent = SimpleNamespace(bot=self.bot, chat=SimpleNamespace(id=100), message_id=55)

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))
        return self.sent


def analytics_data(projects):
    return {
        "ordinary_income": 0.0,
        "ordinary_expense": 60.0,
        "recurring_income": 0.0,
        "recurring_expense": 0.0,
        "recurring_income_count": 0,
        "recurring_expense_count": 0,
        "balance": -60.0,
        "operations": 2,
        "average_check": 30.0,
        "average_day": 30.0,
        "users": [],
        "categories": [],
        "biggest": SimpleNamespace(
            created_at=datetime(2026, 8, 3), title="Шпаклевка", amount=40.0,
        ),
        "projects": projects,
    }


class ProjectAnalyticsServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_sql_groups_sums_sorts_and_limits_family_month_expenses(self):
        session = Session([("Ремонт", 40), ("Италия 2026", 20)])
        with patch.object(statistics_service, "SessionLocal", return_value=session):
            result = await statistics_service.get_project_expense_statistics(7, 2026, 8)
        self.assertEqual(result, [("Ремонт", 40.0), ("Италия 2026", 20.0)])

        sql = str(session.statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
        )).lower()
        self.assertIn("sum(transactions.amount)", sql)
        self.assertIn("group by projects.id, projects.name", sql)
        self.assertIn("order by sum(transactions.amount) desc", sql)
        self.assertIn("limit 5", sql)
        self.assertIn("transactions.family_id = 7", sql)
        self.assertIn("projects.family_id = 7", sql)
        self.assertIn("transactions.type = 'expense'", sql)
        self.assertIn("transactions.project_id is not null", sql)
        self.assertIn("transactions.created_at >= '2026-08-01", sql)
        self.assertIn("transactions.created_at < '2026-09-01", sql)
        self.assertNotIn("projects.is_active", sql)

    async def test_project_slice_does_not_change_general_expense_totals(self):
        stats = {
            "ordinary_income": 10.0, "ordinary_expense": 60.0,
            "recurring_income": 0.0, "recurring_expense": 0.0,
            "recurring_income_count": 0, "recurring_expense_count": 0,
            "balance": -50.0,
        }
        with patch.object(statistics_service, "get_month_statistics", AsyncMock(return_value=stats)), \
             patch.object(statistics_service, "get_month_transactions", AsyncMock(return_value=[])), \
             patch.object(
                 statistics_service, "get_project_expense_statistics",
                 AsyncMock(return_value=[("Ремонт", 40.0)]),
             ):
            data = await statistics_service.get_analytics(7, 2026, 8)
        self.assertEqual(data["ordinary_expense"], 60.0)
        self.assertEqual(data["balance"], -50.0)
        self.assertEqual(data["projects"], [("Ремонт", 40.0)])


class ProjectAnalyticsHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_analytics_screen_shows_top_projects_after_biggest_purchase_html_safe(self):
        message = Message()
        data = analytics_data([("Ремонт <A&B>", 40.0), ("Италия 2026", 20.0)])
        with patch.object(statistics, "get_analytics", AsyncMock(return_value=data)):
            await statistics.analytics(message, 2026, 8, family_id=7)
        text = message.answers[0][0]
        self.assertIn("🏷 <b>Проекты</b>", text)
        self.assertIn("1. Ремонт &lt;A&amp;B&gt;", text)
        self.assertIn("2. Италия 2026", text)
        self.assertGreater(text.index("🏷 <b>Проекты</b>"), text.index("Крупнейшая покупка"))

    async def test_analytics_without_project_expenses_has_no_project_block(self):
        message = Message()
        with patch.object(statistics, "get_analytics", AsyncMock(return_value=analytics_data([]))):
            await statistics.analytics(message, 2026, 8, family_id=7)
        self.assertNotIn("🏷 <b>Проекты</b>", message.answers[0][0])
