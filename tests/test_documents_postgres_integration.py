import asyncio
import os
import unittest
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import uuid4
from unittest.mock import AsyncMock

from sqlalchemy import delete, select

from app.database.db import SessionLocal, engine
from app.database.models import (
    Document, DocumentCategory, DocumentFile, Family, TemporaryTelegramMessage, User,
)
from app.services.document_service import create_or_append_document_file
from app.services.temporary_message_service import (
    claim_due_temporary_messages, schedule_temporary_message_delete, utc_now,
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
class DocumentPostgresConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        unique = uuid4().hex
        self.telegram_id = -(int(unique[:15], 16))
        async with SessionLocal() as session:
            family = Family(name="Documents concurrency test", invite_code=unique[:12])
            session.add(family)
            await session.flush()
            user = User(
                telegram_id=self.telegram_id,
                name="Concurrency tester",
                family_id=family.id,
            )
            category = DocumentCategory(
                family_id=family.id,
                name="Concurrency",
                emoji="test",
                sort_order=0,
                is_system=False,
                is_active=True,
            )
            session.add_all([user, category])
            await session.commit()
            self.family_id = family.id
            self.user_id = user.id
            self.category_id = category.id

    async def asyncTearDown(self):
        try:
            async with SessionLocal() as session:
                await session.execute(delete(Document).where(Document.family_id == self.family_id))
                await session.execute(delete(TemporaryTelegramMessage).where(
                    TemporaryTelegramMessage.chat_id == self.telegram_id,
                ))
                await session.execute(delete(DocumentCategory).where(DocumentCategory.family_id == self.family_id))
                await session.execute(delete(User).where(User.family_id == self.family_id))
                await session.execute(delete(Family).where(Family.id == self.family_id))
                await session.commit()
        finally:
            # IsolatedAsyncioTestCase creates one event loop per test. Do not
            # carry asyncpg pooled connections into the next closed loop.
            await engine.dispose()

    @staticmethod
    def _file(suffix: str, *, unique_id: str | None = None) -> dict:
        return {
            "telegram_file_id": f"file-{suffix}",
            "telegram_file_unique_id": unique_id or f"unique-{suffix}",
            "file_type": "photo",
            "original_filename": None,
            "mime_type": "image/jpeg",
        }

    async def _store(self, upload_key: str, file_data: dict, **overrides):
        return await create_or_append_document_file(
            overrides.get("telegram_id", self.telegram_id),
            upload_key,
            overrides.get("category_id", self.category_id),
            "Concurrent document",
            "Tester",
            "private",
            file_data,
        )

    async def _counts_and_orders(self, upload_key: str):
        async with SessionLocal() as session:
            document_ids = list((await session.execute(
                select(Document.id).where(Document.upload_session_key == upload_key)
            )).scalars())
            files = list((await session.execute(
                select(DocumentFile.document_id, DocumentFile.sort_order)
                .where(DocumentFile.document_id.in_(document_ids))
                .order_by(DocumentFile.sort_order)
            )).all())
        return document_ids, files

    async def test_simultaneous_first_uploads_create_one_document_and_two_files(self):
        upload_key = str(uuid4())
        results = await asyncio.gather(
            self._store(upload_key, self._file("first-a")),
            self._store(upload_key, self._file("first-b")),
        )
        document_ids, files = await self._counts_and_orders(upload_key)
        self.assertEqual(len(document_ids), 1)
        self.assertEqual(len(files), 2)
        self.assertEqual({row.document_id for row in files}, {document_ids[0]})
        self.assertEqual({row.sort_order for row in files}, {0, 1})
        self.assertTrue(all(result is not None for result in results))

    async def test_simultaneous_append_assigns_distinct_sort_order(self):
        upload_key = str(uuid4())
        await self._store(upload_key, self._file("initial"))
        results = await asyncio.gather(
            self._store(upload_key, self._file("append-a")),
            self._store(upload_key, self._file("append-b")),
        )
        document_ids, files = await self._counts_and_orders(upload_key)
        self.assertEqual(len(document_ids), 1)
        self.assertEqual(len(files), 3)
        self.assertEqual([row.sort_order for row in files], [0, 1, 2])
        self.assertEqual(sorted(result.file_count for result in results), [2, 3])

    async def test_simultaneous_duplicate_file_is_noop(self):
        upload_key = str(uuid4())
        results = await asyncio.gather(
            self._store(upload_key, self._file("duplicate-a", unique_id="same-file")),
            self._store(upload_key, self._file("duplicate-b", unique_id="same-file")),
        )
        document_ids, files = await self._counts_and_orders(upload_key)
        self.assertEqual(len(document_ids), 1)
        self.assertEqual(len(files), 1)
        self.assertEqual(sorted(result.file_added for result in results), [False, True])
        self.assertEqual([result.file_count for result in results], [1, 1])

    async def test_upload_key_cannot_cross_creator_or_family(self):
        upload_key = str(uuid4())
        await self._store(upload_key, self._file("owned"))
        unique = uuid4().hex
        other_telegram_id = -(int(unique[:15], 16))
        other_family_telegram_id = -(int(unique[15:30], 16))
        async with SessionLocal() as session:
            same_family_user = User(
                telegram_id=other_telegram_id,
                name="Other creator",
                family_id=self.family_id,
            )
            other_family = Family(name="Other family", invite_code=unique[:12])
            session.add_all([same_family_user, other_family])
            await session.flush()
            other_family_user = User(
                telegram_id=other_family_telegram_id,
                name="Other family creator",
                family_id=other_family.id,
            )
            other_category = DocumentCategory(
                family_id=other_family.id,
                name="Other category",
                emoji="test",
                sort_order=0,
                is_system=False,
                is_active=True,
            )
            session.add_all([other_family_user, other_category])
            await session.commit()
            other_family_id = other_family.id
            other_category_id = other_category.id

        try:
            same_family_result = await self._store(
                upload_key, self._file("attacker"), telegram_id=other_telegram_id,
            )
            other_family_result = await self._store(
                upload_key,
                self._file("other-family"),
                telegram_id=other_family_telegram_id,
                category_id=other_category_id,
            )
            self.assertIsNone(same_family_result)
            self.assertIsNone(other_family_result)
            document_ids, files = await self._counts_and_orders(upload_key)
            self.assertEqual(len(document_ids), 1)
            self.assertEqual(len(files), 1)
        finally:
            async with SessionLocal() as session:
                await session.execute(delete(DocumentCategory).where(
                    DocumentCategory.family_id == other_family_id,
                ))
                await session.execute(delete(User).where(User.family_id == other_family_id))
                await session.execute(delete(Family).where(Family.id == other_family_id))
                await session.execute(delete(User).where(User.telegram_id == other_telegram_id))
                await session.commit()

    async def test_preview_queue_deletion_does_not_change_document_metadata(self):
        upload_key = str(uuid4())
        result = await self._store(upload_key, self._file("preserved"))
        document_id = result.document.id
        file_id = result.file.id
        deadline = utc_now()
        await schedule_temporary_message_delete(self.telegram_id, 900, deadline)
        claimed = await claim_due_temporary_messages(now=deadline)
        queue_task = next(task for task in claimed if task.chat_id == self.telegram_id)
        bot = SimpleNamespace(delete_message=AsyncMock())
        await process_temporary_message(bot, queue_task)

        async with SessionLocal() as session:
            document = await session.get(Document, document_id)
            document_file = await session.get(DocumentFile, file_id)
        self.assertIsNotNone(document)
        self.assertIsNotNone(document_file)
        self.assertEqual(document_file.telegram_file_id, "file-preserved")
        self.assertEqual(document_file.telegram_file_unique_id, "unique-preserved")


if __name__ == "__main__":
    unittest.main()
