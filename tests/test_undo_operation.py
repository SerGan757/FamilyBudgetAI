import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers import expenses
from app.i18n import t
from app.i18n.translations import SUPPORTED_LANGUAGES
from app.keyboards.undo import UndoOperationCallback, undo_operation_keyboard
from app.services import undo_service


class FakeSession:
    def __init__(self, operation):
        self.operation = operation
        self.deleted = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def scalar(self, _query):
        return self.operation

    async def delete(self, operation):
        self.deleted.append(operation)

    async def commit(self):
        self.commits += 1


def operation(**overrides):
    values = {
        "id": 174, "family_id": 7, "user_id": 3,
        "created_at": datetime(2026, 8, 12, 10, 0),
        "is_recurring": False, "project_id": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class UndoServiceTests(unittest.IsolatedAsyncioTestCase):
    async def call(self, kind, item, **overrides):
        session = FakeSession(item)
        with patch.object(undo_service, "SessionLocal", return_value=session), patch.object(
            undo_service, "touch_family_activity", AsyncMock(),
        ):
            result = await undo_service.undo_recent_operation(
                kind, 174, overrides.get("family_id", 7), overrides.get("user_id", 3),
                now=overrides.get("now", datetime(2026, 8, 12, 10, 0, 30)),
            )
        return result, session

    async def test_expense_income_and_project_transaction_can_be_undone(self):
        for item in (operation(type="expense"), operation(type="income"), operation(type="expense", project_id=9)):
            with self.subTest(item=item):
                result, session = await self.call("transaction", item)
                self.assertEqual(result.status, "deleted")
                self.assertEqual(session.deleted, [item])
                self.assertEqual(session.commits, 1)

    async def test_goal_contribution_deletes_only_contribution(self):
        contribution = operation(goal_id=4, amount=500)
        result, session = await self.call("goal", contribution)
        self.assertEqual(result.status, "deleted")
        self.assertEqual(session.deleted, [contribution])

    async def test_different_user_in_same_family_is_not_author(self):
        result, session = await self.call("transaction", operation(), user_id=99)
        self.assertEqual(result.status, "not_author")
        self.assertFalse(session.deleted)

    async def test_different_family_is_denied(self):
        result, session = await self.call("transaction", operation(), family_id=99)
        self.assertEqual(result.status, "forbidden")
        self.assertFalse(session.deleted)

    async def test_59_60_61_second_boundaries(self):
        for seconds, expected in ((59, "deleted"), (60, "deleted"), (61, "expired")):
            with self.subTest(seconds=seconds):
                result, session = await self.call(
                    "transaction", operation(),
                    now=datetime(2026, 8, 12, 10, 0) + timedelta(seconds=seconds),
                )
                self.assertEqual(result.status, expected)
                self.assertEqual(bool(session.deleted), expected == "deleted")

    async def test_goal_contribution_requires_its_author(self):
        result, session = await self.call("goal", operation(goal_id=4), user_id=99)
        self.assertEqual(result.status, "not_author")
        self.assertFalse(session.deleted)

    async def test_transaction_requires_its_author(self):
        result, session = await self.call("transaction", operation(), user_id=99)
        self.assertEqual(result.status, "not_author")
        self.assertFalse(session.deleted)

    async def test_missing_operation_is_safe(self):
        result, session = await self.call("transaction", None)
        self.assertEqual(result.status, "already_deleted")
        self.assertFalse(session.deleted)

    async def test_recurring_transaction_is_not_eligible(self):
        result, session = await self.call("transaction", operation(is_recurring=True))
        self.assertEqual(result.status, "forbidden")
        self.assertFalse(session.deleted)

    def test_undo_never_manipulates_sequence_or_ids(self):
        source = open("app/services/undo_service.py", encoding="utf-8").read().lower()
        self.assertNotIn("sequence", source)
        self.assertNotIn("setval", source)
        self.assertIn("with_for_update", source)


class UndoKeyboardAndHandlerTests(unittest.IsolatedAsyncioTestCase):
    def test_expense_income_and_goal_callbacks_are_typed(self):
        for kind in ("transaction", "goal"):
            data = undo_operation_keyboard(kind, 174, "en").inline_keyboard[0][0].callback_data
            callback = UndoOperationCallback.unpack(data)
            self.assertEqual((callback.kind, callback.operation_id), (kind, 174))

    def test_i18n_keys_exist_for_all_supported_languages(self):
        for language in SUPPORTED_LANGUAGES:
            for key in ("undo.button", "undo.done", "undo.expired", "undo.deleted", "undo.forbidden", "undo.author_only"):
                with self.subTest(language=language, key=key):
                    self.assertNotEqual(t(language, key), key)

    async def test_success_edits_confirmation_and_removes_button(self):
        message = SimpleNamespace(
            chat=SimpleNamespace(id=10, type="private"), edit_text=AsyncMock(), answer=AsyncMock(),
        )
        callback = SimpleNamespace(
            message=message, from_user=SimpleNamespace(id=55), answer=AsyncMock(),
        )
        family = SimpleNamespace(id=7, language="en")
        user = SimpleNamespace(id=3, family_id=7)
        result = undo_service.UndoResult("deleted", 174, "transaction")
        with patch.object(expenses, "require_family_for_chat", AsyncMock(return_value=family)), patch.object(
            expenses, "get_user_by_telegram_id", AsyncMock(return_value=user),
        ), patch.object(expenses, "undo_recent_operation", AsyncMock(return_value=result)):
            await expenses.undo_operation_callback(
                callback, UndoOperationCallback(kind="transaction", operation_id=174),
            )
        message.edit_text.assert_awaited_once_with(t("en", "undo.done"))
        message.answer.assert_not_awaited()
        callback.answer.assert_awaited_once_with()

    async def test_already_deleted_forbidden_and_not_author_are_safe(self):
        for status, expected in (("already_deleted", "undo.deleted"), ("forbidden", "undo.forbidden"), ("not_author", "undo.author_only")):
            message = SimpleNamespace(chat=SimpleNamespace(id=10, type="private"), edit_text=AsyncMock())
            callback = SimpleNamespace(message=message, from_user=SimpleNamespace(id=55), answer=AsyncMock())
            family, user = SimpleNamespace(id=7, language="en"), SimpleNamespace(id=3, family_id=7)
            result = undo_service.UndoResult(status, 174, "transaction")
            with patch.object(expenses, "require_family_for_chat", AsyncMock(return_value=family)), patch.object(
                expenses, "get_user_by_telegram_id", AsyncMock(return_value=user),
            ), patch.object(expenses, "undo_recent_operation", AsyncMock(return_value=result)):
                await expenses.undo_operation_callback(callback, UndoOperationCallback(kind="transaction", operation_id=174))
            callback.answer.assert_awaited_once_with(t("en", expected), show_alert=True)
            message.edit_text.assert_not_awaited()


class UndoConfirmationTests(unittest.IsolatedAsyncioTestCase):
    def message(self, text):
        return SimpleNamespace(
            text=text,
            from_user=SimpleNamespace(id=55, full_name="Ann", language_code="en"),
            chat=SimpleNamespace(id=10, type="private", title=None),
            answer=AsyncMock(),
        )

    def state(self):
        return SimpleNamespace(update_data=AsyncMock(), set_state=AsyncMock())

    async def test_single_expense_and_income_confirmations_have_undo(self):
        family = SimpleNamespace(id=7, language="en", currency="EUR")
        user = SimpleNamespace(id=3, family_id=7)
        for text, operation_type in (("coffee 5", "expense"), ("+2000 salary", "income")):
            message = self.message(text)
            saved = SimpleNamespace(
                id=174, type=operation_type, title="coffee", amount=5,
                category="📦 Other", project_name=None,
            )
            with patch.object(expenses, "require_family_for_chat", AsyncMock(return_value=family)), patch.object(
                expenses, "get_user_by_telegram_id", AsyncMock(return_value=user),
            ), patch.object(expenses, "save_transaction", AsyncMock(return_value=saved)):
                await expenses.add_transaction(message, self.state())
            markup = message.answer.await_args.kwargs["reply_markup"]
            callback = UndoOperationCallback.unpack(markup.inline_keyboard[0][0].callback_data)
            self.assertEqual((callback.kind, callback.operation_id), ("transaction", 174))

    async def test_single_goal_contribution_confirmation_has_undo(self):
        family = SimpleNamespace(id=7, language="en", currency="EUR")
        user = SimpleNamespace(id=3, family_id=7)
        contribution = SimpleNamespace(id=175, amount=500)
        goal = SimpleNamespace(name="Car", target_amount=1000)
        snapshot = SimpleNamespace(goal=goal, saved=500, remaining=500)
        message = self.message("++500")
        with patch.object(expenses, "require_family_for_chat", AsyncMock(return_value=family)), patch.object(
            expenses, "get_user_by_telegram_id", AsyncMock(return_value=user),
        ), patch.object(expenses, "add_contribution", AsyncMock(return_value=contribution)), patch.object(
            expenses, "get_goal_snapshot", AsyncMock(return_value=snapshot),
        ):
            await expenses.add_transaction(message, self.state())
        markup = message.answer.await_args.kwargs["reply_markup"]
        callback = UndoOperationCallback.unpack(markup.inline_keyboard[0][0].callback_data)
        self.assertEqual((callback.kind, callback.operation_id), ("goal", 175))

    async def test_batch_confirmation_has_no_undo(self):
        family = SimpleNamespace(id=7, language="en", currency="EUR")
        user = SimpleNamespace(id=3, family_id=7)
        saved = [
            SimpleNamespace(id=174, type="expense", title="A", amount=5, category="📦 Other", project_name=None),
            SimpleNamespace(id=175, type="expense", title="B", amount=6, category="📦 Other", project_name=None),
        ]
        message = self.message("A 5\nB 6")
        with patch.object(expenses, "require_family_for_chat", AsyncMock(return_value=family)), patch.object(
            expenses, "get_user_by_telegram_id", AsyncMock(return_value=user),
        ), patch.object(expenses, "save_transaction", AsyncMock(side_effect=saved)):
            await expenses.add_transaction(message, self.state())
        markup = message.answer.await_args.kwargs["reply_markup"]
        self.assertFalse(hasattr(markup, "inline_keyboard"))


if __name__ == "__main__":
    unittest.main()
