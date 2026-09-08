import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app import main as app_main


class MainLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_stops_before_runtime_resources_close(self):
        events = []
        bot = SimpleNamespace(
            session=SimpleNamespace(
                close=AsyncMock(side_effect=lambda: events.append("bot_closed")),
            ),
        )
        dispatcher = SimpleNamespace(
            include_router=Mock(),
            start_polling=AsyncMock(side_effect=lambda *args, **kwargs: events.append("polling_stopped")),
        )
        web_runner = SimpleNamespace(
            cleanup=AsyncMock(side_effect=lambda: events.append("web_closed")),
        )
        test_engine = SimpleNamespace(
            dispose=AsyncMock(side_effect=lambda: events.append("db_closed")),
        )

        async def worker(_bot, stop_event):
            events.append("worker_started")
            await stop_event.wait()
            events.append("worker_stopped")

        with patch.object(app_main, "BOT_TOKEN", "test-token"), patch.object(
            app_main, "init_db", AsyncMock(),
        ), patch.object(
            app_main, "start_web_server", AsyncMock(return_value=web_runner),
        ), patch.object(
            app_main, "Bot", return_value=bot,
        ), patch.object(
            app_main, "Dispatcher", return_value=dispatcher,
        ), patch.object(
            app_main, "run_temporary_message_worker", worker,
        ), patch.object(app_main, "engine", test_engine):
            await app_main.main()

        dispatcher.start_polling.assert_awaited_once_with(
            bot, close_bot_session=False,
        )
        self.assertEqual(events.count("worker_started"), 1)
        self.assertLess(events.index("worker_stopped"), events.index("bot_closed"))
        self.assertLess(events.index("worker_stopped"), events.index("db_closed"))


if __name__ == "__main__":
    unittest.main()
