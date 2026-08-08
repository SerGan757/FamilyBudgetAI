import unittest
from pathlib import Path

from app.database.models import Family


class TemporaryScreenTtlMigrationTests(unittest.TestCase):
    def test_model_default_is_twenty_and_not_nullable(self):
        column = Family.__table__.c.temporary_screen_ttl
        self.assertFalse(column.nullable)
        self.assertEqual(column.default.arg, 20)
        self.assertEqual(str(column.server_default.arg), "20")

    def test_controlled_migration_backfills_default_and_not_null(self):
        sql = Path("docs/migrations/20260808_add_temporary_screen_ttl.sql").read_text(
            encoding="utf-8",
        ).lower()
        self.assertIn("add column if not exists temporary_screen_ttl integer", sql)
        self.assertIn("set temporary_screen_ttl = 20", sql)
        self.assertIn("alter column temporary_screen_ttl set default 20", sql)
        self.assertIn("alter column temporary_screen_ttl set not null", sql)


if __name__ == "__main__":
    unittest.main()
