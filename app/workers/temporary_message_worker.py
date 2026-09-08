import asyncio
import logging
from datetime import timedelta

from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramNotFound,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)

from app.services.temporary_message_service import (
    ClaimedTemporaryMessage,
    claim_due_temporary_messages,
    cleanup_failed_temporary_messages,
    complete_temporary_message,
    fail_temporary_message,
    retry_temporary_message,
    utc_now,
)


logger = logging.getLogger(__name__)

WORKER_BATCH_SIZE = 50
WORKER_LEASE_SECONDS = 60
WORKER_POLL_SECONDS = 1.0
RETRY_DELAYS = (5, 30, 120)
FAILED_RETENTION_DAYS = 7
FAILED_CLEANUP_INTERVAL_SECONDS = 3600


def _message_is_already_absent(error: TelegramBadRequest) -> bool:
    description = str(error).lower()
    return (
        "message to delete not found" in description
        or "message not found" in description
        or "message already deleted" in description
    )


def _permanent_error(error: TelegramAPIError) -> bool:
    if isinstance(
        error, (TelegramForbiddenError, TelegramNotFound, TelegramUnauthorizedError),
    ):
        return True
    if isinstance(error, TelegramBadRequest):
        return not _message_is_already_absent(error)
    return False


def _retry_delay(task: ClaimedTemporaryMessage, error: TelegramAPIError) -> int | None:
    if task.attempts >= len(RETRY_DELAYS):
        return None
    delay = RETRY_DELAYS[task.attempts]
    if isinstance(error, TelegramRetryAfter):
        delay = max(delay, int(error.retry_after))
    return delay


async def process_temporary_message(
    bot,
    task: ClaimedTemporaryMessage,
) -> None:
    try:
        await bot.delete_message(chat_id=task.chat_id, message_id=task.message_id)
    except TelegramBadRequest as error:
        if _message_is_already_absent(error):
            await complete_temporary_message(task.id)
            return
        await fail_temporary_message(task.id, attempts=task.attempts + 1)
        logger.info(
            "TEMPORARY_MESSAGE_DELETE_FAILED task_id=%s chat_id=%s message_id=%s "
            "attempt=%s error=%s",
            task.id, task.chat_id, task.message_id, task.attempts + 1,
            type(error).__name__,
        )
    except (TelegramRetryAfter, TelegramNetworkError, TelegramServerError) as error:
        delay = _retry_delay(task, error)
        if delay is None:
            await fail_temporary_message(task.id, attempts=task.attempts + 1)
        else:
            await retry_temporary_message(
                task.id,
                attempts=task.attempts + 1,
                delete_after=utc_now() + timedelta(seconds=delay),
            )
        logger.info(
            "TEMPORARY_MESSAGE_DELETE_RETRY task_id=%s chat_id=%s message_id=%s "
            "attempt=%s error=%s",
            task.id, task.chat_id, task.message_id, task.attempts + 1,
            type(error).__name__,
        )
    except TelegramAPIError as error:
        if _permanent_error(error):
            await fail_temporary_message(task.id, attempts=task.attempts + 1)
        else:
            delay = _retry_delay(task, error)
            if delay is None:
                await fail_temporary_message(task.id, attempts=task.attempts + 1)
            else:
                await retry_temporary_message(
                    task.id,
                    attempts=task.attempts + 1,
                    delete_after=utc_now() + timedelta(seconds=delay),
                )
        logger.info(
            "TEMPORARY_MESSAGE_DELETE_SKIPPED task_id=%s chat_id=%s message_id=%s "
            "attempt=%s error=%s",
            task.id, task.chat_id, task.message_id, task.attempts + 1,
            type(error).__name__,
        )
    else:
        await complete_temporary_message(task.id)


async def process_due_temporary_messages(bot) -> int:
    tasks = await claim_due_temporary_messages(
        batch_size=WORKER_BATCH_SIZE,
        lease_seconds=WORKER_LEASE_SECONDS,
    )
    for task in tasks:
        try:
            await process_temporary_message(bot, task)
        except Exception as error:
            logger.exception(
                "TEMPORARY_MESSAGE_WORKER_TASK_ERROR task_id=%s chat_id=%s "
                "message_id=%s error=%s",
                task.id, task.chat_id, task.message_id, type(error).__name__,
            )
    return len(tasks)


async def run_temporary_message_worker(bot, stop_event: asyncio.Event) -> None:
    next_cleanup_at = 0.0
    while not stop_event.is_set():
        try:
            loop_time = asyncio.get_running_loop().time()
            if loop_time >= next_cleanup_at:
                next_cleanup_at = loop_time + FAILED_CLEANUP_INTERVAL_SECONDS
                await cleanup_failed_temporary_messages(
                    before=utc_now() - timedelta(days=FAILED_RETENTION_DAYS),
                )
            processed = await process_due_temporary_messages(bot)
        except Exception as error:
            processed = 0
            logger.exception(
                "TEMPORARY_MESSAGE_WORKER_ERROR error=%s", type(error).__name__,
            )
        if processed:
            continue
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=WORKER_POLL_SECONDS)
        except TimeoutError:
            pass
