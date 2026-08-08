import asyncio
import logging

from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message


TEMPORARY_SCREEN_TTL = 20

logger = logging.getLogger(__name__)
_delete_tasks: dict[tuple[int, int], asyncio.Task[None]] = {}


async def _delete_after(
    bot,
    chat_id: int,
    message_id: int,
    ttl: float,
) -> None:
    key = (chat_id, message_id)
    try:
        await asyncio.sleep(ttl)
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except asyncio.CancelledError:
        raise
    except TelegramAPIError as error:
        logger.debug(
            "TEMPORARY_SCREEN_DELETE_SKIPPED chat_id=%s message_id=%s error=%s",
            chat_id, message_id, type(error).__name__,
        )
    finally:
        current = asyncio.current_task()
        if _delete_tasks.get(key) is current:
            _delete_tasks.pop(key, None)


def schedule_temporary_delete(
    bot,
    chat_id: int,
    message_id: int,
    *,
    ttl: float = TEMPORARY_SCREEN_TTL,
) -> asyncio.Task[None] | None:
    key = (chat_id, message_id)
    old_task = _delete_tasks.get(key)
    if old_task is not None and not old_task.done():
        old_task.cancel()
    _delete_tasks.pop(key, None)
    if ttl <= 0:
        return None
    task = asyncio.create_task(_delete_after(bot, chat_id, message_id, ttl))
    _delete_tasks[key] = task
    return task


def refresh_temporary_delete(
    bot,
    chat_id: int,
    message_id: int,
    *,
    ttl: float = TEMPORARY_SCREEN_TTL,
) -> asyncio.Task[None] | None:
    return schedule_temporary_delete(
        bot, chat_id, message_id, ttl=ttl,
    )


def cancel_temporary_delete(chat_id: int, message_id: int) -> None:
    task = _delete_tasks.pop((chat_id, message_id), None)
    if task is not None and not task.done():
        task.cancel()


def schedule_temporary_message(message: Message, *, ttl: float = TEMPORARY_SCREEN_TTL) -> asyncio.Task[None] | None:
    return schedule_temporary_delete(
        message.bot, message.chat.id, message.message_id, ttl=ttl,
    )


def refresh_temporary_message(message: Message, *, ttl: float = TEMPORARY_SCREEN_TTL) -> asyncio.Task[None] | None:
    return refresh_temporary_delete(
        message.bot, message.chat.id, message.message_id, ttl=ttl,
    )
