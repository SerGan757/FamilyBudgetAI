import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import inspect

from app.database.models import GoalContribution, SavingsGoal
from app.handlers import expenses, statistics
from app.handlers.savings_goal import goal_card
from app.i18n import t
from app.i18n.translations import SUPPORTED_LANGUAGES
from app.services import delete_service, savings_goal_service
from app.services.parser import parse_message
from app.services.savings_goal_service import GoalSnapshot, calculate_observed_pace, progress_bar


class SavingsGoalParserTests(unittest.TestCase):
    def test_expense_income_and_goal_are_distinct(self):
        self.assertEqual(parse_message("200")["type"], "expense")
        self.assertEqual(parse_message("+300")["type"], "income")
        for text in ("++500", "++ 500", "++500 машина", "++500 €"):
            with self.subTest(text=text):
                parsed = parse_message(text)
                self.assertEqual(parsed["type"], "goal_contribution")
                self.assertEqual(parsed["amount"], 500)


class SavingsGoalSchemaTests(unittest.TestCase):
    def test_models_keep_contributions_separate_from_transactions(self):
        self.assertEqual(SavingsGoal.__tablename__, "savings_goals")
        self.assertEqual(GoalContribution.__tablename__, "goal_contributions")
        self.assertNotIn("saved", inspect(SavingsGoal).columns)
        self.assertIn("goal_id", inspect(GoalContribution).columns)
        self.assertIn("family_id", inspect(GoalContribution).columns)
        self.assertIn("user_id", inspect(GoalContribution).columns)

    def test_controlled_migration_has_safe_constraints_and_indexes(self):
        source = Path("docs/migrations/20260809_add_savings_goals.sql").read_text(encoding="utf-8").lower()
        self.assertIn("where is_active = true", source)
        self.assertIn("references families(id) on delete cascade", source)
        self.assertIn("references users(id) on delete cascade", source)
        self.assertIn("references savings_goals(id) on delete cascade", source)
        self.assertIn("ix_goal_contributions_created_at", source)
        self.assertIn("pg_get_serial_sequence('transactions', 'id')", source)
        self.assertNotIn("create table goal_contributions (\n    id serial", source)
        self.assertNotIn("alter table transactions", source)


class SavingsGoalFormattingTests(unittest.TestCase):
    def test_short_observation_does_not_create_absurd_monthly_pace(self):
        average, days, expected, monthly = calculate_observed_pace(
            date(2026, 8, 9), date(2026, 8, 9), 1100, 18900,
        )
        self.assertIsNone(average)
        self.assertIsNone(days)
        self.assertIsNone(expected)
        self.assertIsNone(monthly)

    def test_seven_day_observation_enables_capped_30_day_algorithm(self):
        average, days, expected, monthly = calculate_observed_pace(
            date(2026, 8, 1), date(2026, 8, 8), 800, 1600,
        )
        self.assertEqual(average, 100)
        self.assertEqual(days, 16)
        self.assertIsNotNone(expected)
        self.assertLess(monthly, 4000)

    def test_progress_is_capped_and_remaining_never_negative(self):
        self.assertEqual(progress_bar(0, 100), "░░░░░░░░░░ 0%")
        self.assertEqual(progress_bar(68, 100), "███████░░░ 68%")
        self.assertEqual(progress_bar(150, 100), "██████████ 150%")

    def test_card_uses_family_currency_and_does_not_translate_name(self):
        goal = SimpleNamespace(name="Машина", target_amount=20000, deadline=None)
        snapshot = GoalSnapshot(goal=goal, saved=7000, remaining=13000, percentage=35)
        text = goal_card(snapshot, "PLN", "de")
        self.assertIn("Машина", text)
        self.assertIn("7 000.00 zł", text)
        self.assertIn("13 000.00 zł", text)

    def test_goal_translation_catalog_covers_all_languages(self):
        for language in SUPPORTED_LANGUAGES:
            for key in ("settings.savings_goal", "goal.create", "goal.saved", "goal.no_active_for_contribution"):
                self.assertNotEqual(t(language, key), key)


def analytics_data(goal=None):
    return {
        "ordinary_income": 1000.0, "ordinary_expense": 400.0,
        "recurring_income": 0.0, "recurring_expense": 0.0,
        "recurring_income_count": 0, "recurring_expense_count": 0,
        "balance": 600.0, "operations": 2, "average_check": 200.0,
        "average_day": 200.0, "users": [], "categories": [],
        "biggest": None, "projects": [], "goal": goal,
    }


class SavingsGoalAnalyticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_short_history_shows_required_amount_but_hides_current_pace(self):
        goal = SimpleNamespace(name="Car", target_amount=20000, deadline=date(2027, 1, 31))
        snapshot = GoalSnapshot(
            goal=goal, saved=1100, remaining=18900, percentage=5.5,
            month_contributions=1100, required_per_month=3500,
            average_per_day=None, current_per_month=None, days_to_goal=None,
            expected_date=None, pace_difference=None, schedule_months=None,
        )
        message = SimpleNamespace(answer=AsyncMock())
        with patch.object(statistics, "get_analytics", AsyncMock(return_value=analytics_data(snapshot))):
            await statistics.analytics(message, 2026, 8, family_id=7, language="en")
        text = message.answer.await_args.args[0]
        self.assertIn("Required saving: 3 500.00 €/month", text)
        self.assertIn("Not enough data for a forecast", text)
        self.assertNotIn("Current saving pace", text)
        self.assertNotIn("Ahead of pace", text)
        self.assertNotIn("Expected date", text)

    async def test_goal_is_separate_and_free_balance_uses_selected_month_only(self):
        goal = SimpleNamespace(name="Car <X>", target_amount=2000, deadline=None)
        snapshot = GoalSnapshot(
            goal=goal, saved=700, remaining=1300, percentage=35,
            month_contributions=100, average_per_day=10,
            days_to_goal=130, expected_date=date(2027, 1, 1),
        )
        message = SimpleNamespace(answer=AsyncMock())
        with patch.object(statistics, "get_analytics", AsyncMock(return_value=analytics_data(snapshot))):
            await statistics.analytics(message, 2026, 8, family_id=7, language="en")
        text = message.answer.await_args.args[0]
        self.assertIn("Car &lt;X&gt;", text)
        self.assertIn("This month: +100.00 €", text)
        self.assertIn("Free balance: 500.00 €", text)
        self.assertIn("Ordinary expenses: <b>400.00 €</b>", text)

    async def test_without_goal_existing_analytics_is_unchanged(self):
        message = SimpleNamespace(answer=AsyncMock())
        with patch.object(statistics, "get_analytics", AsyncMock(return_value=analytics_data())):
            await statistics.analytics(message, 2026, 8, family_id=7, language="en")
        self.assertNotIn("Savings goal", message.answer.await_args.args[0])


class _Session:
    def __init__(self, scalars):
        self.scalars = iter(scalars)
        self.added = []
        self.committed = False

    async def __aenter__(self): return self
    async def __aexit__(self, *args): return None
    async def scalar(self, statement): return next(self.scalars)
    def add(self, value): self.added.append(value)
    async def commit(self): self.committed = True
    async def refresh(self, value): value.id = 1


class SavingsGoalIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_user_in_family_creates_no_contribution(self):
        session = _Session([None, SimpleNamespace(id=9)])
        with patch.object(savings_goal_service, "SessionLocal", return_value=session):
            result = await savings_goal_service.add_contribution(7, 123, 500)
        self.assertIsNone(result)
        self.assertEqual(session.added, [])
        self.assertFalse(session.committed)

    async def test_contribution_stores_internal_user_and_family_ids(self):
        session = _Session([SimpleNamespace(id=4), SimpleNamespace(id=9)])
        with patch.object(savings_goal_service, "SessionLocal", return_value=session):
            result = await savings_goal_service.add_contribution(7, 123456789, 500)
        self.assertEqual(result.user_id, 4)
        self.assertEqual(result.goal_id, 9)
        self.assertEqual(result.family_id, 7)
        self.assertNotEqual(result.user_id, 123456789)


class _DeleteResult:
    def __init__(self, row):
        self.row = row

    def one_or_none(self):
        return self.row


class _DeleteSession:
    def __init__(self, transaction=None, contribution_row=None):
        self.transaction = transaction
        self.contribution_row = contribution_row
        self.deleted = []
        self.committed = False

    async def __aenter__(self): return self
    async def __aexit__(self, *args): return None
    async def scalar(self, statement): return self.transaction
    async def execute(self, statement): return _DeleteResult(self.contribution_row)
    async def delete(self, value): self.deleted.append(value)
    async def commit(self): self.committed = True


class UnifiedOperationDeleteTests(unittest.IsolatedAsyncioTestCase):
    async def test_numeric_id_deletes_goal_contribution_in_family(self):
        contribution = SimpleNamespace(id=15, amount=500)
        session = _DeleteSession(contribution_row=(contribution, "Car"))
        with patch.object(delete_service, "SessionLocal", return_value=session), \
             patch.object(delete_service, "touch_family_activity", AsyncMock()):
            result = await delete_service.delete_operation_by_id(15, 7)
        self.assertEqual(result.id, 15)
        self.assertEqual(result.type, "goal_contribution")
        self.assertEqual(session.deleted, [contribution])
        self.assertTrue(session.committed)

    async def test_numeric_id_prefers_transaction(self):
        transaction = SimpleNamespace(id=16, title="Coffee", amount=5, type="expense")
        session = _DeleteSession(transaction=transaction)
        with patch.object(delete_service, "SessionLocal", return_value=session), \
             patch.object(delete_service, "touch_family_activity", AsyncMock()):
            result = await delete_service.delete_operation_by_id(16, 7)
        self.assertEqual(result.id, 16)
        self.assertEqual(result.type, "expense")
        self.assertEqual(session.deleted, [transaction])

    async def test_unknown_id_does_not_delete_anything(self):
        session = _DeleteSession()
        with patch.object(delete_service, "SessionLocal", return_value=session):
            result = await delete_service.delete_operation_by_id(999, 7)
        self.assertIsNone(result)
        self.assertEqual(session.deleted, [])
        self.assertFalse(session.committed)


if __name__ == "__main__":
    unittest.main()
