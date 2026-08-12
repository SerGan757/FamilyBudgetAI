import inspect
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import inspect as sa_inspect

from app.data.categories import CATEGORIES
from app.database.models import FamilyCategoryKeywordOverride
from app.handlers import categories
from app.i18n import t
from app.i18n.translations import SUPPORTED_LANGUAGES
from app.keyboards.categories import categories_keyboard, category_card_keyboard
from app.services import category_override_service as overrides
from app.services.category_service import detect_category, detect_category_for_family


class ScalarResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class Session:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.added = []
        self.deleted = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def execute(self, statement):
        self.statement = statement
        return ScalarResult(self.rows)

    def add(self, row):
        self.added.append(row)

    async def delete(self, row):
        self.deleted.append(row)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def row(family_id, key, keyword, action, row_id=1):
    return SimpleNamespace(
        id=row_id, family_id=family_id, category_key=key, keyword=keyword,
        normalized_keyword=overrides.normalize_keyword(keyword), action=action,
    )


class CategorySchemaTests(unittest.TestCase):
    def test_override_model_contract(self):
        mapper = sa_inspect(FamilyCategoryKeywordOverride)
        self.assertEqual(mapper.local_table.name, "family_category_keyword_overrides")
        self.assertEqual(
            {column.name for column in mapper.columns},
            {"id", "family_id", "category_key", "keyword", "normalized_keyword", "action", "created_at"},
        )
        constraints = {constraint.name for constraint in mapper.local_table.constraints}
        self.assertIn("ck_family_category_keyword_action", constraints)
        self.assertIn("uq_family_category_keyword_override", constraints)

    def test_controlled_migration_and_init_exclusion(self):
        root = Path(__file__).resolve().parents[1]
        sql = (root / "docs/migrations/20260812_add_family_category_keyword_overrides.sql").read_text("utf-8")
        init = (root / "app/database/init_db.py").read_text("utf-8")
        self.assertIn("ON DELETE CASCADE", sql)
        self.assertIn("CHECK (action IN ('add', 'disable'))", sql)
        self.assertIn("UNIQUE (family_id, category_key, normalized_keyword)", sql)
        self.assertIn('"family_category_keyword_overrides"', init)


class EffectiveKeywordTests(unittest.IsolatedAsyncioTestCase):
    def test_normalization(self):
        self.assertEqual(overrides.normalize_keyword("  Royal   Canin "), "royal canin")
        self.assertEqual(overrides.normalize_keyword("   "), "")

    async def test_without_overrides_matches_system_behavior(self):
        catalog = overrides._build_catalog([])
        with patch.object(
            overrides, "get_effective_category_catalog", AsyncMock(return_value=catalog),
        ):
            self.assertEqual(
                await detect_category_for_family(1, "пицца", "expense"),
                detect_category("пицца", "expense"),
            )

    async def test_disable_is_family_scoped_and_disabled_word_does_not_score(self):
        family_one = overrides._build_catalog([row(1, "products", "еда", "disable")])
        family_two = overrides._build_catalog([])
        with patch.object(
            overrides, "get_effective_category_catalog",
            AsyncMock(side_effect=[family_one, family_two]),
        ):
            self.assertNotEqual(await detect_category_for_family(1, "Еда вне дома"), ("🛒", "Продукты"))
            self.assertEqual(await detect_category_for_family(2, "Еда вне дома"), ("🛒", "Продукты"))

    async def test_family_added_keyword_and_unknown_fallback(self):
        family_one = overrides._build_catalog([row(1, "animals", "груминг", "add")])
        family_two = overrides._build_catalog([])
        with patch.object(
            overrides, "get_effective_category_catalog",
            AsyncMock(side_effect=[family_one, family_two]),
        ):
            self.assertEqual(await detect_category_for_family(1, "груминг"), ("🐾", "Животные"))
            self.assertEqual(await detect_category_for_family(2, "груминг"), ("📦", "Прочее"))

    async def test_income_is_never_overridden(self):
        self.assertEqual(await detect_category_for_family(1, "anything", "income"), ("💰", "Доход"))

    async def test_conflict_and_duplicate_are_rejected(self):
        session = Session()
        with patch.object(overrides, "SessionLocal", return_value=session):
            conflict = await overrides.add_family_keyword(1, "products", "кофе")
        self.assertEqual(conflict.status, "conflict")
        self.assertEqual(conflict.conflict_category_key, "cafe")
        self.assertEqual(session.added, [])

        session = Session()
        with patch.object(overrides, "SessionLocal", return_value=session):
            duplicate = await overrides.add_family_keyword(1, "products", "еда")
        self.assertEqual(duplicate.status, "duplicate")
        self.assertEqual(session.added, [])

    async def test_system_disable_family_add_delete_and_restore(self):
        session = Session()
        with patch.object(overrides, "SessionLocal", return_value=session):
            result = await overrides.disable_family_keyword(1, "products", "еда")
        self.assertEqual(result.status, "disabled")
        self.assertEqual(session.added[0].action, "disable")

        added = row(1, "animals", "груминг", "add")
        session = Session([added])
        with patch.object(overrides, "SessionLocal", return_value=session):
            result = await overrides.disable_family_keyword(1, "animals", "груминг")
        self.assertEqual(result.status, "removed")
        self.assertEqual(session.deleted, [added])


class BulkKeywordTests(unittest.IsolatedAsyncioTestCase):
    def test_single_bulk_spaces_empty_duplicates_and_phrase(self):
        self.assertEqual(overrides.parse_keyword_list("ветеринар"), ["ветеринар"])
        self.assertEqual(
            overrides.parse_keyword_list("  Кот , кошка,  Royal   Canin ,, корм "),
            ["кот", "кошка", "royal canin", "корм"],
        )
        self.assertEqual(
            overrides.parse_keyword_list("кот, КОТ, кот"), ["кот"],
        )
        self.assertEqual(overrides.parse_keyword_list("royal canin"), ["royal canin"])

    async def test_limit_31_rejects_everything_and_30_is_allowed(self):
        mutate = AsyncMock(return_value=overrides.KeywordMutationResult("added"))
        with patch.object(overrides, "add_family_keyword", mutate):
            rejected = await overrides.add_family_keywords(
                7, "animals", ",".join(f"word{i}" for i in range(31)),
            )
        self.assertTrue(rejected.limit_exceeded)
        mutate.assert_not_awaited()

        mutate.reset_mock()
        with patch.object(overrides, "add_family_keyword", mutate):
            accepted = await overrides.add_family_keywords(
                7, "animals", ",".join(f"word{i}" for i in range(30)),
            )
        self.assertFalse(accepted.limit_exceeded)
        self.assertEqual(accepted.count("added"), 30)
        self.assertEqual(mutate.await_count, 30)
        self.assertTrue(all(call.args[0] == 7 for call in mutate.await_args_list))

    async def test_partial_success_existing_restore_and_conflict(self):
        mutate = AsyncMock(side_effect=[
            overrides.KeywordMutationResult("added"),
            overrides.KeywordMutationResult("duplicate"),
            overrides.KeywordMutationResult("conflict", "children"),
            overrides.KeywordMutationResult("restored"),
        ])
        with patch.object(overrides, "add_family_keyword", mutate):
            result = await overrides.add_family_keywords(
                7, "animals", "груминг, ветеринар, игрушка, кот",
            )
        self.assertEqual(result.count("added"), 1)
        self.assertEqual(result.count("already_exists"), 1)
        self.assertEqual(result.count("conflict"), 1)
        self.assertEqual(result.count("restored"), 1)
        conflict = next(item for item in result.items if item.status == "conflict")
        self.assertEqual(conflict.keyword, "игрушка")
        self.assertEqual(conflict.conflict_category_key, "children")

    async def test_disabled_system_word_is_restored_not_added(self):
        disabled = row(7, "animals", "кот", "disable")
        session = Session([disabled])
        with patch.object(overrides, "SessionLocal", return_value=session):
            result = await overrides.add_family_keyword(7, "animals", "кот")
        self.assertEqual(result.status, "restored")
        self.assertEqual(session.deleted, [disabled])
        self.assertEqual(session.added, [])

    async def test_family_added_duplicate_is_already_exists(self):
        mutate = AsyncMock(return_value=overrides.KeywordMutationResult("duplicate"))
        with patch.object(overrides, "add_family_keyword", mutate):
            result = await overrides.add_family_keywords(7, "animals", "груминг")
        self.assertEqual(result.count("already_exists"), 1)

    def test_bulk_i18n_exists_for_every_locale(self):
        keys = (
            "category.add", "category.bulk_title", "category.bulk_prompt",
            "category.bulk_max", "category.bulk_added", "category.bulk_restored",
            "category.bulk_existing", "category.bulk_conflicting",
            "category.bulk_conflicts", "category.bulk_limit",
        )
        for language in SUPPORTED_LANGUAGES:
            for key in keys:
                self.assertNotEqual(t(language, key), key)

    async def test_cancel_returns_to_card_and_clears_state(self):
        callback = SimpleNamespace(
            message=SimpleNamespace(chat=SimpleNamespace(id=10, type="private")),
            from_user=SimpleNamespace(id=1), answer=AsyncMock(),
        )
        state = AsyncMock()
        family = SimpleNamespace(id=7, language="en", temporary_screen_ttl=20)
        data = SimpleNamespace(action="card", key="animals", value="settings")
        with patch.object(categories, "_family", AsyncMock(return_value=family)), \
             patch.object(categories, "show_category_card", AsyncMock(return_value=True)) as show:
            await categories.category_callback(callback, data, state)
        state.clear.assert_awaited_once()
        show.assert_awaited_once_with(callback.message, family, "animals", 0, "settings")

    async def test_handler_summary_localizes_conflict_category(self):
        message = SimpleNamespace(
            text="груминг, игрушка",
            chat=SimpleNamespace(id=10, type="private"),
            from_user=SimpleNamespace(id=1), answer=AsyncMock(),
        )
        state = AsyncMock()
        state.get_data.return_value = {
            "category_key": "animals", "category_origin": "settings", "family_id": 7,
        }
        family = SimpleNamespace(id=7, language="en")
        result = overrides.BulkKeywordResult((
            overrides.BulkKeywordItemResult("груминг", "added"),
            overrides.BulkKeywordItemResult("игрушка", "conflict", "children"),
        ))
        with patch.object(categories, "_family", AsyncMock(return_value=family)), \
             patch.object(categories, "add_family_keywords", AsyncMock(return_value=result)), \
             patch.object(categories, "get_effective_keywords", AsyncMock(return_value=[])):
            await categories.save_category_keyword(message, state)
        text = message.answer.await_args.args[0]
        self.assertIn("Added: 1", text)
        self.assertIn("Conflicting: 1", text)
        self.assertIn("игрушка → 👨‍👩‍👧 Children", text)


class CategoryUiTests(unittest.IsolatedAsyncioTestCase):
    def test_settings_list_card_pagination_and_all_locales(self):
        catalog = overrides._build_catalog([])
        keyboard = categories_keyboard(catalog, "en")
        callbacks = [b.callback_data for row_ in keyboard.inline_keyboard for b in row_]
        self.assertTrue(any("cat:card:animals" in value for value in callbacks))
        self.assertTrue(any("cat:card:other" in value for value in callbacks))
        card = category_card_keyboard("other", "en", 0, origin="settings")
        labels = [b.text for row_ in card.inline_keyboard for b in row_]
        self.assertNotIn("➕ Add keyword", labels)
        self.assertIn("📋 Category transactions", labels)
        paged = category_card_keyboard("products", "en", 0, origin="settings", total=30)
        self.assertTrue(any(button.text == "➡️" for row_ in paged.inline_keyboard for button in row_))
        for language in SUPPORTED_LANGUAGES:
            self.assertNotEqual(t(language, "category.title"), "category.title")
            self.assertNotEqual(t(language, "category.add"), "category.add")

    async def test_drilldown_contains_rows_totals_author_date_and_family_scope(self):
        message = SimpleNamespace(edit_text=AsyncMock())
        family = SimpleNamespace(id=7, language="en", currency="EUR")
        transaction = SimpleNamespace(
            id=167, title="Cat food", amount=45.0, user_name="Sergey",
            created_at=datetime(2026, 8, 5),
        )
        with patch.object(
            categories, "get_transactions_by_category_page",
            AsyncMock(return_value=([transaction], 3, 100.0)),
        ) as query:
            ok = await categories.show_category_operations(
                message, family, "animals", "settings|2026-08|0",
            )
        self.assertTrue(ok)
        query.assert_awaited_once()
        self.assertEqual(query.await_args.args[0], 7)
        text = message.edit_text.await_args.args[0]
        self.assertIn("167 Cat food -45.00 € Sergey 05.08.2026", text)
        self.assertIn("Total: 100.00 €", text)
        self.assertIn("Transactions: 3", text)
        markup = message.edit_text.await_args.kwargs["reply_markup"]
        callbacks = [b.callback_data for row_ in markup.inline_keyboard for b in row_]
        self.assertTrue(any("2026-07" in value for value in callbacks))
        self.assertTrue(any("2026-09" in value for value in callbacks))
        self.assertTrue(any("|all|" in value for value in callbacks))

    def test_family_filter_is_present_in_drilldown_service(self):
        from app.services import history_service
        source = inspect.getsource(history_service.get_transactions_by_category)
        self.assertIn("Transaction.family_id == family_id", source)
        self.assertIn("Transaction.created_at >= start", source)
        self.assertIn("Transaction.created_at < end", source)


if __name__ == "__main__":
    unittest.main()
