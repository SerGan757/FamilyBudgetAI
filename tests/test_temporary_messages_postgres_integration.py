import asyncio
import os
import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlparse
from uuid import uuid4

from aiogram.exceptions import TelegramNetworkError
from sqlalchemy import delete, func, select, update

from app.database.db import SessionLocal, engine
from app.database.models import TemporaryTelegramMessage
from app.services.temporary_message_service import (
    FAILED,
    PENDING,
    PROCESSING,
    claim_due_temporary_messages,
    schedule_temporary_message_delete,
    utc_now,
)
from app.workers.temporary_message_worker import process_temporary_message


def _local_test_database_is_explicitly_enabled() -> bool:
    if os.getenv("RUN_POSTGRES_DOCUMENTS_INTEGRATION") != "1":
        return False
    database_url = os.getenv("DATABASE_URL", "").replace(
        "postgresql+asyncpg://", "postgresql://", 1,
    )
    parsed = urlparse(database_url)
    return (
        parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        and parsed.path.removeprefix("/").endswith("_test")
    )


@unittest.skipUnless(
    _local_test_database_is_explicitly_enabled(),
    "requires an explicitly enabled loopback PostgreSQL *_test database",
)
class TemporaryMessagePostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.chat_id = -(int(uuid4().hex[:15], 16))

    async def asyncTearDown(self):
        try:
            async with SessionLocal() as session:
                await session.execute(delete(TemporaryTelegramMessage).where(
                    TemporaryTelegramMessage.chat_id == self.chat_id,
                ))
                await session.commit()
        finally:
            await engine.dispose()

    async def _row(self, message_id: int):
        async with SessionLocal() as session:
            return (await session.execute(select(TemporaryTelegramMessage).where(
                TemporaryTelegramMessage.chat_id == self.chat_id,
                TemporaryTelegramMessage.message_id == message_id,
            ))).scalar_one_or_none()

    async def test_duplicate_schedule_upserts_one_row_and_latest_deadline(self):
        first = utc_now() + timedelta(minutes=1)
        second = first + timedelta(minutes=2)
        await schedule_temporary_message_delete(self.chat_id, 10, first)
        await schedule_temporary_message_delete(self.chat_id, 10, second)
        async with SessionLocal() as session:
            count = (await session.execute(select(func.count()).select_from(
                TemporaryTelegramMessage,
            ).where(
                TemporaryTelegramMessage.chat_id == self.chat_id,
                TemporaryTelegramMessage.message_id == 10,
            ))).scalar_one()
        row = await self._row(10)
        self.assertEqual(count, 1)
        self.assertEqual(row.delete_after, second)
        self.assertEqual(row.status, PENDING)
        self.assertEqual(row.attempts, 0)
        self.assertIsNone(row.locked_until)

    async def test_persistent_row_is_claimed_by_new_service_and_completed(self):
        deadline = utc_now() + timedelta(seconds=10)
        await schedule_temporary_message_delete(self.chat_id, 11, deadline)
        # No worker object or in-memory task is retained here. A later service
        # invocation represents a newly started process after the deadline.
        claimed = await claim_due_temporary_messages(
            now=deadline + timedelta(seconds=1), lease_seconds=60,
        )
        matching = [task for task in claimed if task.chat_id == self.chat_id]
        self.assertEqual(len(matching), 1)
        bot = SimpleNamespace(delete_message=AsyncMock())
        await process_temporary_message(bot, matching[0])
        bot.delete_message.assert_awaited_once_with(chat_id=self.chat_id, message_id=11)
        self.assertIsNone(await self._row(11))

    async def test_two_claimers_cannot_claim_same_row(self):
        now = utc_now()
        await schedule_temporary_message_delete(self.chat_id, 12, now)
        first, second = await asyncio.gather(
            claim_due_temporary_messages(now=now, lease_seconds=60),
            claim_due_temporary_messages(now=now, lease_seconds=60),
        )
        matching = [
            task for batch in (first, second) for task in batch
            if task.chat_id == self.chat_id
        ]
        self.assertEqual(len(matching), 1)

    async def test_expired_processing_lease_is_recovered(self):
        now = utc_now()
        await schedule_temporary_message_delete(self.chat_id, 13, now)
        claimed = await claim_due_temporary_messages(now=now, lease_seconds=60)
        self.assertEqual(len([x for x in claimed if x.chat_id == self.chat_id]), 1)
        before_expiry = await claim_due_temporary_messages(
            now=now + timedelta(seconds=59), lease_seconds=60,
        )
        self.assertFalse(any(x.chat_id == self.chat_id for x in before_expiry))
        after_expiry = await claim_due_temporary_messages(
            now=now + timedelta(seconds=61), lease_seconds=60,
        )
        self.assertEqual(len([x for x in after_expiry if x.chat_id == self.chat_id]), 1)

    async def test_transient_error_retries_then_retry_limit_fails(self):
        now = utc_now()
        await schedule_temporary_message_delete(self.chat_id, 14, now)
        claimed = await claim_due_temporary_messages(now=now)
        current = next(x for x in claimed if x.chat_id == self.chat_id)
        bot = SimpleNamespace(delete_message=AsyncMock(side_effect=TelegramNetworkError(
            method=SimpleNamespace(), message="network unavailable",
        )))
        await process_temporary_message(bot, current)
        row = await self._row(14)
        self.assertEqual(row.status, PENDING)
        self.assertEqual(row.attempts, 1)

        async with SessionLocal() as session:
            await session.execute(update(TemporaryTelegramMessage).where(
                TemporaryTelegramMessage.id == row.id,
            ).values(
                status=PROCESSING,
                attempts=3,
                locked_until=now + timedelta(seconds=60),
            ))
            await session.commit()
        await process_temporary_message(
            bot,
            type(current)(current.id, current.chat_id, current.message_id, 3),
        )
        row = await self._row(14)
        self.assertEqual(row.status, FAILED)
        self.assertEqual(row.attempts, 4)


if __name__ == "__main__":
    unittest.main()
