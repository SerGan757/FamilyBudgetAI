import unittest
import asyncio
import inspect
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiogram.exceptions import (
    TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError,
    TelegramRetryAfter,
)

from app.services.temporary_message_service import ClaimedTemporaryMessage
from app.workers import temporary_message_worker as worker


def task(attempts=0):
    return ClaimedTemporaryMessage(
        id=7, chat_id=100, message_id=200, attempts=attempts,
    )


class TemporaryMessageWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_stops_without_claiming_after_shutdown_signal(self):
        stop = asyncio.Event()
        stop.set()
        with patch.object(worker, "claim_due_temporary_messages", AsyncMock()) as claim:
            await worker.run_temporary_message_worker(SimpleNamespace(), stop)
        claim.assert_not_awaited()

    def test_worker_logging_does_not_reference_document_metadata(self):
        source = inspect.getsource(worker)
        for forbidden in (
            "telegram_file_id", "telegram_file_unique_id", "document.title",
            "original_filename", "mime_type", "caption",
        ):
            self.assertNotIn(forbidden, source)

    async def test_success_completes_queue_row(self):
        bot = SimpleNamespace(delete_message=AsyncMock())
        with patch.object(worker, "complete_temporary_message", AsyncMock()) as complete:
            await worker.process_temporary_message(bot, task())
        complete.assert_awaited_once_with(7)

    async def test_already_deleted_is_terminal_success(self):
        error = TelegramBadRequest(
            method=Mock(), message="Bad Request: message to delete not found",
        )
        bot = SimpleNamespace(delete_message=AsyncMock(side_effect=error))
        with patch.object(worker, "complete_temporary_message", AsyncMock()) as complete, \
             patch.object(worker, "retry_temporary_message", AsyncMock()) as retry:
            await worker.process_temporary_message(bot, task())
        complete.assert_awaited_once_with(7)
        retry.assert_not_awaited()

    async def test_network_error_uses_bounded_retry_schedule(self):
        error = TelegramNetworkError(method=Mock(), message="network unavailable")
        bot = SimpleNamespace(delete_message=AsyncMock(side_effect=error))
        now = datetime(2026, 9, 7, 12, 0)
        with patch.object(worker, "utc_now", return_value=now), patch.object(
            worker, "retry_temporary_message", AsyncMock(),
        ) as retry:
            await worker.process_temporary_message(bot, task(attempts=1))
        retry.assert_awaited_once()
        self.assertEqual(retry.await_args.kwargs["attempts"], 2)
        self.assertEqual(
            retry.await_args.kwargs["delete_after"].timestamp() - now.timestamp(),
            30,
        )

    async def test_retry_after_uses_larger_telegram_delay(self):
        error = TelegramRetryAfter(
            method=Mock(), message="retry later", retry_after=45,
        )
        bot = SimpleNamespace(delete_message=AsyncMock(side_effect=error))
        now = datetime(2026, 9, 7, 12, 0)
        with patch.object(worker, "utc_now", return_value=now), patch.object(
            worker, "retry_temporary_message", AsyncMock(),
        ) as retry:
            await worker.process_temporary_message(bot, task(attempts=1))
        self.assertEqual(
            retry.await_args.kwargs["delete_after"].timestamp() - now.timestamp(),
            45,
        )

    async def test_retry_limit_and_permanent_error_fail(self):
        cases = (
            (TelegramNetworkError(method=Mock(), message="network"), 3),
            (TelegramForbiddenError(method=Mock(), message="forbidden"), 0),
            (TelegramBadRequest(method=Mock(), message="message can't be deleted"), 0),
        )
        for error, attempts in cases:
            with self.subTest(error=type(error).__name__):
                bot = SimpleNamespace(delete_message=AsyncMock(side_effect=error))
                with patch.object(worker, "fail_temporary_message", AsyncMock()) as fail, \
                     patch.object(worker, "retry_temporary_message", AsyncMock()) as retry:
                    await worker.process_temporary_message(bot, task(attempts=attempts))
                fail.assert_awaited_once_with(7, attempts=attempts + 1)
                retry.assert_not_awaited()

    async def test_one_task_error_does_not_stop_batch(self):
        tasks = [task(), ClaimedTemporaryMessage(8, 101, 201, 0)]
        with patch.object(
            worker, "claim_due_temporary_messages", AsyncMock(return_value=tasks),
        ), patch.object(
            worker, "process_temporary_message",
            AsyncMock(side_effect=[RuntimeError("test"), None]),
        ) as process:
            processed = await worker.process_due_temporary_messages(SimpleNamespace())
        self.assertEqual(processed, 2)
        self.assertEqual(process.await_count, 2)


if __name__ == "__main__":
    unittest.main()
