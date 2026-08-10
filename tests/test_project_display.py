import inspect
import unittest
from types import SimpleNamespace

from app.handlers.history import format_transaction as history_format
from app.handlers.statistics import format_transaction as statistics_format
from app.services import financial_feed_service, history_service, statistics_service
from app.utils.transaction_format import project_suffix


def transaction(*, project_marker=False, project=None):
    values = {
        "id": 1,
        "type": "expense",
        "amount": 20.0,
        "is_recurring": False,
        "title": "кофе",
        "category": "🛒 Продукты",
        "user_name": "Вася",
        "user": SimpleNamespace(name="Вася"),
    }
    if project_marker:
        values["project"] = project
    return SimpleNamespace(**values)


class ProjectDisplayTests(unittest.TestCase):
    def test_operation_without_project_is_unchanged(self):
        row = transaction()
        history = history_format(row)
        today = statistics_format(row)
        self.assertNotIn("🏷", history)
        self.assertNotIn("🏷", today)
        self.assertEqual(project_suffix(row), "")

    def test_project_name_is_appended_without_tag_on_same_line(self):
        project = SimpleNamespace(name="Италия 2026", tag="italy26")
        row = transaction(project_marker=True, project=project)
        for text in (history_format(row), statistics_format(row)):
            self.assertIn("🏷 Италия 2026", text)
            self.assertNotIn("italy26", text)
            self.assertNotIn("\n", text)

    def test_project_html_is_escaped_and_forced_to_one_line(self):
        row = transaction(
            project_marker=True,
            project=SimpleNamespace(name="A < B\n& C", tag="secret"),
        )
        text = history_format(row)
        self.assertIn("🏷 A &lt; B &amp; C", text)
        self.assertNotIn("\n", text)

    def test_missing_project_object_does_not_break_formatter(self):
        row = transaction(project_marker=True, project=None)
        self.assertNotIn("🏷", history_format(row))
        self.assertNotIn("🏷", statistics_format(row))

    def test_list_queries_eager_load_family_scoped_project_without_n_plus_one(self):
        stats_sql = str(statistics_service._transaction_list_query(7)).lower()
        self.assertIn("left outer join projects", stats_sql)
        self.assertIn("projects.family_id", stats_sql)
        history_source = inspect.getsource(history_service.get_last_transactions)
        self.assertIn("get_display_feed", history_source)
        feed_sql = str(financial_feed_service._feed_query(7)).lower()
        self.assertIn("left outer join projects", feed_sql)
        self.assertIn("projects.family_id", feed_sql)
        self.assertIn("union all", feed_sql)
        helper_source = inspect.getsource(project_suffix)
        self.assertNotIn("SessionLocal", helper_source)
        self.assertNotIn("execute", helper_source)
