import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.enums import ChatType

from app.handlers import admin
from app.keyboards.admin import PAGE_SIZE, AdminCallback, admin_families_keyboard
from app.services.admin_auth import is_admin, parse_admin_telegram_ids


def message(*, user_id=123, chat_type=ChatType.PRIVATE):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id), chat=SimpleNamespace(type=chat_type),
        answer=AsyncMock(),
    )


def callback(*, user_id=123, chat_type=ChatType.PRIVATE):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        message=SimpleNamespace(
            chat=SimpleNamespace(type=chat_type), edit_text=AsyncMock(), delete=AsyncMock(),
        ),
        answer=AsyncMock(),
    )


def data(action: str, object_id: int = 0, page: int = 0) -> AdminCallback:
    return AdminCallback(action=action, object_id=object_id, page=page)


class AdminAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    def test_admin_ids_support_multiple_and_ignore_invalid_values(self):
        self.assertEqual(parse_admin_telegram_ids("123, invalid, -2, 456, "), frozenset({123, 456}))
        self.assertEqual(parse_admin_telegram_ids(None), frozenset())

    def test_empty_configuration_denies_everyone(self):
        with patch.dict(os.environ, {"ADMIN_TELEGRAM_IDS": ""}):
            self.assertFalse(is_admin(123))

    async def test_myid_returns_only_callers_id(self):
        msg = message(user_id=765)
        await admin.my_id(msg)
        msg.answer.assert_awaited_once_with("Ваш Telegram ID: 765")

    async def test_admin_in_group_discloses_no_data(self):
        msg = message(chat_type=ChatType.GROUP)
        with patch.object(admin, "is_admin", return_value=True):
            await admin.open_admin(msg)
        msg.answer.assert_awaited_once_with(admin.PRIVATE_ONLY_TEXT)

    async def test_non_admin_gets_no_callback_data(self):
        event = callback()
        with patch.object(admin, "is_admin", return_value=False) as check, \
             patch.object(admin, "get_admin_status", AsyncMock()) as status:
            await admin.admin_callback(event, data("status"))
        check.assert_called_once_with(123)
        status.assert_not_awaited()
        event.answer.assert_awaited_once_with(admin.ACCESS_DENIED_TEXT, show_alert=True)

    async def test_callback_in_group_is_denied_before_database_access(self):
        event = callback(chat_type=ChatType.SUPERGROUP)
        with patch.object(admin, "get_admin_status", AsyncMock()) as status:
            await admin.admin_callback(event, data("status"))
        status.assert_not_awaited()
        event.answer.assert_awaited_once_with(admin.PRIVATE_ONLY_TEXT, show_alert=True)


class AdminPanelTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, callback_data, **mocks):
        event = callback()
        patches = [patch.object(admin, "is_admin", return_value=True)]
        patches.extend(patch.object(admin, name, AsyncMock(return_value=value))
                       for name, value in mocks.items())
        for active_patch in patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)
        await admin.admin_callback(event, callback_data)
        return event

    async def test_family_card(self):
        family = {"id": 4, "name": "Дом <A>", "users": 2,
                  "transactions": 8, "recurring_payments": 3}
        event = await self._run(data("family", 4), get_admin_family=family)
        text = event.message.edit_text.await_args.args[0]
        self.assertIn("ID: 4", text)
        self.assertIn("Дом &lt;A&gt;", text)
        self.assertIn("Участников: 2", text)

    async def test_family_members_are_scoped_and_hide_telegram_id(self):
        event = await self._run(
            data("family_members", 4),
            get_admin_family_members=("Дом", ["Анна", "Борис"]),
        )
        text = event.message.edit_text.await_args.args[0]
        self.assertIn("1. Анна", text)
        self.assertIn("2. Борис", text)
        self.assertNotIn("telegram", text.lower())
        self.assertNotIn("987654321", text)

    async def test_family_statistics(self):
        stats = {"name": "Дом", "income": 100, "expense": 40, "balance": 60,
                 "operations": 3, "recurring_income": 20, "recurring_expense": 10}
        event = await self._run(data("family_stats", 4), get_admin_family_statistics=stats)
        text = event.message.edit_text.await_args.args[0]
        self.assertIn("Доходы за текущий месяц: 100.00 €", text)
        self.assertIn("Баланс за текущий месяц: 60.00 €", text)
        self.assertIn("Регулярных расходов: 10.00 €/мес", text)

    async def test_user_card_hides_telegram_id(self):
        user = {"id": 7, "name": "Анна", "family_id": 4, "family_name": "Дом",
                "operations": 5, "income": 90, "expense": 30}
        event = await self._run(data("user", 7), get_admin_user=user)
        text = event.message.edit_text.await_args.args[0]
        self.assertIn("ID: 7", text)
        self.assertIn("Семья: Дом", text)
        self.assertIn("Доходы за текущий месяц: 90.00 €", text)
        self.assertNotIn("telegram", text.lower())
        self.assertNotIn("987654321", text)

    async def test_missing_family_and_user_are_safe(self):
        for callback_data, service in (
            (data("family", 999), "get_admin_family"),
            (data("family_members", 999), "get_admin_family_members"),
            (data("family_stats", 999), "get_admin_family_statistics"),
            (data("user", 999), "get_admin_user"),
        ):
            event = await self._run(callback_data, **{service: None})
            event.answer.assert_awaited_once_with(admin.NOT_FOUND_TEXT, show_alert=True)
            event.message.edit_text.assert_not_awaited()

    async def test_family_pagination_requests_ten_and_preserves_page(self):
        event = await self._run(
            data("families", page=2),
            get_admin_families_page=([(21, "Семья 21")], 22),
        )
        admin.get_admin_families_page.assert_awaited_once_with(2, PAGE_SIZE)
        keyboard = event.message.edit_text.await_args.kwargs["reply_markup"]
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
        self.assertTrue(any(AdminCallback.unpack(item).page == 1 for item in callbacks if item))
        self.assertFalse(any(AdminCallback.unpack(item).page == 3 for item in callbacks if item))

    def test_pagination_buttons_only_exist_when_page_exists(self):
        first = admin_families_keyboard([(1, "A")], 0, 11)
        first_actions = [AdminCallback.unpack(button.callback_data).action
                         for row in first.inline_keyboard for button in row]
        self.assertIn("families", first_actions)
        last = admin_families_keyboard([(11, "B")], 1, 11)
        pages = [AdminCallback.unpack(button.callback_data).page
                 for row in last.inline_keyboard for button in row
                 if button.callback_data and AdminCallback.unpack(button.callback_data).action == "families"]
        self.assertEqual(pages, [0])
