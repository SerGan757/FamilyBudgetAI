from datetime import timedelta

from aiogram.types import Message

from app.services.temporary_message_service import (
    cancel_temporary_message_delete,
    schedule_temporary_message_delete,
    utc_now,
)


TEMPORARY_SCREEN_TTL = 20


async def schedule_temporary_delete(
    bot,
    chat_id: int,
    message_id: int,
    *,
    ttl: float = TEMPORARY_SCREEN_TTL,
) -> int | None:
    del bot  # The worker owns Telegram API calls; PostgreSQL is the source of truth.
    if ttl <= 0:
        await cancel_temporary_message_delete(chat_id, message_id)
        return None
    return await schedule_temporary_message_delete(
        chat_id,
        message_id,
        utc_now() + timedelta(seconds=ttl),
    )


async def refresh_temporary_delete(
    bot,
    chat_id: int,
    message_id: int,
    *,
    ttl: float = TEMPORARY_SCREEN_TTL,
) -> int | None:
    return await schedule_temporary_delete(
        bot, chat_id, message_id, ttl=ttl,
    )


async def cancel_temporary_delete(chat_id: int, message_id: int) -> None:
    await cancel_temporary_message_delete(chat_id, message_id)


async def schedule_temporary_message(
    message: Message,
    *,
    ttl: float = TEMPORARY_SCREEN_TTL,
) -> int | None:
    return await schedule_temporary_delete(
        message.bot, message.chat.id, message.message_id, ttl=ttl,
    )


async def refresh_temporary_message(
    message: Message,
    *,
    ttl: float = TEMPORARY_SCREEN_TTL,
) -> int | None:
    return await refresh_temporary_delete(
        message.bot, message.chat.id, message.message_id, ttl=ttl,
    )
