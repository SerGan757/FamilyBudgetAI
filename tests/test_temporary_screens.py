import asyncio
import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramBadRequest

from app.handlers import history, menu, recurring, settings, statistics
from app.keyboards.main_menu import main_menu
from app.utils import temporary_screens


def sent_message(chat_id=100, message_id=50):
    return SimpleNamespace(
        bot=SimpleNamespace(delete_message=AsyncMock()),
        chat=SimpleNamespace(id=chat_id),
        message_id=message_id,
    )


def incoming_message():
    return SimpleNamespace(
        chat=SimpleNamespace(id=100, type="private"),
        from_user=SimpleNamespace(id=1),
        answer=AsyncMock(return_value=sent_message()),
    )


def month_data():
    return {
        "income": 0.0, "expense": 0.0,
        "ordinary_income": 0.0, "ordinary_expense": 0.0,
        "recurring_income": 0.0, "recurring_expense": 0.0,
        "recurring_income_count": 0, "recurring_expense_count": 0,
        "balance": 0.0, "transactions": [], "total": 0,
    }


def analytics_data():
    return {
        **month_data(), "operations": 0, "average_check": 0.0,
        "average_day": 0.0, "users": [], "categories": [],
        "biggest": None, "projects": [],
    }


class TemporaryScreenManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        tasks = list(temporary_screens._delete_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        temporary_screens._delete_tasks.clear()

    async def test_refresh_cancels_old_timer_and_keeps_one_current_task(self):
        bot = SimpleNamespace(delete_message=AsyncMock())
        first = temporary_screens.schedule_temporary_delete(bot, 1, 10, ttl=60)
        second = temporary_screens.refresh_temporary_delete(bot, 1, 10, ttl=60)
        await asyncio.sleep(0)
        self.assertTrue(first.cancelled())
        self.assertIs(temporary_screens._delete_tasks[(1, 10)], second)
        self.assertEqual(len(temporary_screens._delete_tasks), 1)

    async def test_missing_message_delete_error_is_safely_ignored(self):
        bot = SimpleNamespace(delete_message=AsyncMock(side_effect=TelegramBadRequest(
            method=SimpleNamespace(), message="Bad Request: message to delete not found",
        )))
        task = temporary_screens.schedule_temporary_delete(bot, 1, 10, ttl=0.001)
        await task
        self.assertNotIn((1, 10), temporary_screens._delete_tasks)

    async def test_off_does_not_create_delete_task(self):
        bot = SimpleNamespace(delete_message=AsyncMock())
        task = temporary_screens.schedule_temporary_delete(bot, 1, 10, ttl=0)
        self.assertIsNone(task)
        self.assertNotIn((1, 10), temporary_screens._delete_tasks)
        bot.delete_message.assert_not_awaited()

    async def test_different_messages_and_chats_have_independent_timers(self):
        bot = SimpleNamespace(delete_message=AsyncMock())
        first = temporary_screens.schedule_temporary_delete(bot, 1, 10, ttl=60)
        second = temporary_screens.schedule_temporary_delete(bot, 1, 11, ttl=60)
        third = temporary_screens.schedule_temporary_delete(bot, 2, 10, ttl=60)
        self.assertEqual(len(temporary_screens._delete_tasks), 3)
        temporary_screens.cancel_temporary_delete(1, 10)
        await asyncio.sleep(0)
        self.assertTrue(first.cancelled())
        self.assertFalse(second.cancelled())
        self.assertFalse(third.cancelled())


class TemporaryScreenHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_initial_reports_schedule_delete(self):
        cases = (
            (history, history.history, {"get_transactions_count": 0, "build_history_text": "History"}),
            (statistics, statistics.today, {"get_today_statistics": month_data()}),
            (statistics, statistics.month, {"get_month_statistics": month_data()}),
            (statistics, statistics.analytics, {"get_analytics": analytics_data()}),
        )
        for module, handler, services in cases:
            with self.subTest(handler=handler.__name__):
                message, sent = incoming_message(), sent_message()
                schedule_patcher = patch.object(module, "schedule_temporary_message")
                patches = [
                    patch.object(module, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=3, temporary_screen_ttl=20))),
                    patch.object(module, "answer_with_navigation", AsyncMock(return_value=sent)),
                    schedule_patcher,
                ]
                for name, value in services.items():
                    patches.append(patch.object(
                        module, name,
                        AsyncMock(return_value=value) if not isinstance(value, str) else AsyncMock(return_value=value),
                    ))
                entered = [item.start() for item in patches]
                schedule = entered[2]
                try:
                    if handler is statistics.analytics:
                        await handler(message, 2026, 8)
                    else:
                        await handler(message)
                finally:
                    for item in reversed(patches):
                        item.stop()
                schedule.assert_called_once_with(sent, ttl=20)

    async def test_balance_schedules_its_sent_message(self):
        message, sent = incoming_message(), sent_message()
        message.answer.return_value = sent
        with patch.object(
            statistics, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=3, temporary_screen_ttl=20)),
        ), patch.object(
            statistics, "get_balance", AsyncMock(return_value=month_data()),
        ), patch.object(statistics, "schedule_temporary_message") as schedule:
            await statistics.balance(message)
        schedule.assert_called_once_with(sent, ttl=20)
        self.assertNotIn("reply_markup", message.answer.await_args.kwargs)
        self.assertEqual(message.answer.await_count, 1)
        self.assertNotIn("\u2063", message.answer.await_args.args[0])

    async def test_main_menu_installs_persistent_reply_keyboard_once(self):
        message = incoming_message()
        with patch.object(
            menu, "require_family_for_chat",
            AsyncMock(return_value=SimpleNamespace(language="ru")),
        ):
            await menu.show_menu(message)
        message.answer.assert_awaited_once()
        self.assertEqual(message.answer.await_args.kwargs["reply_markup"], main_menu)
        self.assertTrue(main_menu.is_persistent)
        self.assertNotIn("\u2063", message.answer.await_args.args[0])

    async def test_analytics_navigation_help_and_back_refresh_same_message(self):
        callback_message = SimpleNamespace(
            bot=SimpleNamespace(), chat=SimpleNamespace(id=100, type="private"),
            message_id=50, edit_text=AsyncMock(), answer=AsyncMock(),
        )
        event = SimpleNamespace(
            data="analytics:2026:07", message=callback_message,
            from_user=SimpleNamespace(id=1), answer=AsyncMock(),
        )
        with patch.object(
            statistics, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=3, temporary_screen_ttl=20)),
        ), patch.object(
            statistics, "get_analytics", AsyncMock(return_value=analytics_data()),
        ), patch.object(statistics, "refresh_temporary_message") as refresh:
            await statistics.analytics_page(event)
        refresh.assert_called_once_with(callback_message, ttl=20)
        callback_message.answer.assert_not_awaited()

        for data, handler in (
            ("analytics_help:2026:07", statistics.analytics_help),
            ("analytics_back:2026:07", statistics.analytics_back),
        ):
            event.data = data
            event.answer.reset_mock()
            with patch.object(
                statistics, "require_family_for_chat", AsyncMock(return_value=SimpleNamespace(id=3, temporary_screen_ttl=20)),
            ), patch.object(
                statistics, "get_analytics", AsyncMock(return_value=analytics_data()),
            ), patch.object(statistics, "refresh_temporary_message") as refresh:
                await handler(event)
            refresh.assert_called_once_with(callback_message, ttl=20)
            event.answer.assert_awaited_once_with()

    def test_settings_and_recurring_do_not_schedule_temporary_deletes(self):
        self.assertNotIn("schedule_temporary", inspect.getsource(settings))
        self.assertNotIn("temporary_screen", inspect.getsource(recurring))


if __name__ == "__main__":
    unittest.main()
