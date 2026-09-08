from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

from app.database.db import SessionLocal
from app.database.models import TemporaryTelegramMessage


PENDING = "pending"
PROCESSING = "processing"
FAILED = "failed"


def utc_now() -> datetime:
    """Return naive UTC to match the project's PostgreSQL datetime convention."""
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class ClaimedTemporaryMessage:
    id: int
    chat_id: int
    message_id: int
    attempts: int


async def schedule_temporary_message_delete(
    chat_id: int,
    message_id: int,
    delete_after: datetime,
) -> int:
    statement = postgresql_insert(TemporaryTelegramMessage).values(
        chat_id=chat_id,
        message_id=message_id,
        delete_after=delete_after,
        attempts=0,
        status=PENDING,
        locked_until=None,
        last_attempt_at=None,
    ).on_conflict_do_update(
        constraint="uq_temporary_telegram_messages_chat_message",
        set_={
            "delete_after": delete_after,
            "attempts": 0,
            "status": PENDING,
            "locked_until": None,
            "last_attempt_at": None,
        },
    ).returning(TemporaryTelegramMessage.id)
    async with SessionLocal() as session:
        task_id = (await session.execute(statement)).scalar_one()
        await session.commit()
        return task_id


async def cancel_temporary_message_delete(chat_id: int, message_id: int) -> None:
    async with SessionLocal() as session:
        await session.execute(delete(TemporaryTelegramMessage).where(
            TemporaryTelegramMessage.chat_id == chat_id,
            TemporaryTelegramMessage.message_id == message_id,
        ))
        await session.commit()


async def claim_due_temporary_messages(
    *,
    now: datetime | None = None,
    batch_size: int = 50,
    lease_seconds: int = 60,
) -> list[ClaimedTemporaryMessage]:
    now = now or utc_now()
    locked_until = now + timedelta(seconds=lease_seconds)
    due = or_(
        and_(
            TemporaryTelegramMessage.status == PENDING,
            TemporaryTelegramMessage.delete_after <= now,
        ),
        and_(
            TemporaryTelegramMessage.status == PROCESSING,
            TemporaryTelegramMessage.locked_until.is_not(None),
            TemporaryTelegramMessage.locked_until <= now,
        ),
    )
    statement = (
        select(TemporaryTelegramMessage)
        .where(due)
        .order_by(TemporaryTelegramMessage.delete_after, TemporaryTelegramMessage.id)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    async with SessionLocal() as session:
        rows = list((await session.execute(statement)).scalars())
        for row in rows:
            row.status = PROCESSING
            row.locked_until = locked_until
        await session.commit()
        return [
            ClaimedTemporaryMessage(
                id=row.id,
                chat_id=row.chat_id,
                message_id=row.message_id,
                attempts=row.attempts,
            )
            for row in rows
        ]


async def complete_temporary_message(task_id: int) -> None:
    async with SessionLocal() as session:
        await session.execute(delete(TemporaryTelegramMessage).where(
            TemporaryTelegramMessage.id == task_id,
        ))
        await session.commit()


async def retry_temporary_message(
    task_id: int,
    *,
    attempts: int,
    delete_after: datetime,
) -> None:
    async with SessionLocal() as session:
        await session.execute(update(TemporaryTelegramMessage).where(
            TemporaryTelegramMessage.id == task_id,
            TemporaryTelegramMessage.status == PROCESSING,
        ).values(
            attempts=attempts,
            status=PENDING,
            delete_after=delete_after,
            locked_until=None,
            last_attempt_at=utc_now(),
        ))
        await session.commit()


async def fail_temporary_message(task_id: int, *, attempts: int) -> None:
    async with SessionLocal() as session:
        await session.execute(update(TemporaryTelegramMessage).where(
            TemporaryTelegramMessage.id == task_id,
            TemporaryTelegramMessage.status == PROCESSING,
        ).values(
            attempts=attempts,
            status=FAILED,
            locked_until=None,
            last_attempt_at=utc_now(),
        ))
        await session.commit()


async def cleanup_failed_temporary_messages(*, before: datetime) -> int:
    async with SessionLocal() as session:
        result = await session.execute(delete(TemporaryTelegramMessage).where(
            TemporaryTelegramMessage.status == FAILED,
            TemporaryTelegramMessage.last_attempt_at < before,
        ))
        await session.commit()
        return result.rowcount or 0
