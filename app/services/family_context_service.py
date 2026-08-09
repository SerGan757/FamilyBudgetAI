import logging
import secrets
import string

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.db import SessionLocal
from app.database.models import Family, User


logger = logging.getLogger(__name__)


class FamilyContextConflictError(RuntimeError):
    """Raised when legacy families cannot be safely mapped to one chat."""


class FamilyContextNotFoundError(RuntimeError):
    """Raised when a financial request arrives from an unbound chat."""


def _invite_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(12))


async def get_family_by_chat_id(chat_id: int) -> Family | None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Family).where(Family.telegram_chat_id == chat_id)
        )
        family = result.scalar_one_or_none()
        if family is not None:
            logger.info("FAMILY_CONTEXT_FOUND chat_id=%s", chat_id)
        return family


async def get_family_by_user_telegram_id(telegram_id: int) -> Family | None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Family)
            .join(User, User.family_id == Family.id)
            .where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


async def require_family_for_chat(
    chat_id: int,
    *,
    chat_type: str | None = None,
    telegram_id: int | None = None,
) -> Family:
    """Read-only context lookup for financial handlers; never creates a family."""
    if chat_type == "private":
        family = (
            await get_family_by_user_telegram_id(telegram_id)
            if telegram_id is not None
            else None
        )
    else:
        family = await get_family_by_chat_id(chat_id)
    if family is None:
        raise FamilyContextNotFoundError("The Telegram chat is not bound to a family.")
    return family


async def bind_legacy_family_to_chat(
    chat_id: int,
    chat_title: str | None = None,
) -> Family:
    """Bind the only unbound legacy family; never choose one arbitrarily."""
    async with SessionLocal() as session:
        existing = await session.execute(
            select(Family).where(Family.telegram_chat_id == chat_id)
        )
        family = existing.scalar_one_or_none()
        if family is not None:
            logger.info("FAMILY_CONTEXT_FOUND chat_id=%s", chat_id)
            return family

        legacy_result = await session.execute(
            select(Family).where(Family.telegram_chat_id.is_(None))
        )
        legacy_families = legacy_result.scalars().all()
        if len(legacy_families) != 1:
            raise FamilyContextConflictError(
                "Legacy family binding requires exactly one unbound family."
            )

        family = legacy_families[0]
        family.telegram_chat_id = chat_id
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            result = await session.execute(
                select(Family).where(Family.telegram_chat_id == chat_id)
            )
            bound = result.scalar_one_or_none()
            if bound is None:
                raise
            return bound

        await session.refresh(family)
        logger.info("LEGACY_FAMILY_BOUND family_id=%s chat_id=%s", family.id, chat_id)
        return family


async def get_or_create_family_for_chat(
    chat_id: int,
    chat_title: str | None = None,
    initial_language: str = "ru",
) -> Family:
    family = await get_family_by_chat_id(chat_id)
    if family is not None:
        return family

    async with SessionLocal() as session:
        legacy_result = await session.execute(
            select(Family).where(Family.telegram_chat_id.is_(None))
        )
        legacy_families = legacy_result.scalars().all()

    if len(legacy_families) == 1:
        return await bind_legacy_family_to_chat(chat_id, chat_title)
    if len(legacy_families) > 1:
        logger.warning("FAMILY_CONTEXT_CONFLICT chat_id=%s", chat_id)
        raise FamilyContextConflictError(
            "More than one legacy family requires an explicit binding."
        )

    for _ in range(3):
        async with SessionLocal() as session:
            family = Family(
                telegram_chat_id=chat_id,
                name=chat_title or f"Семья {chat_id}",
                invite_code=_invite_code(),
                language=initial_language,
            )
            session.add(family)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.execute(
                    select(Family).where(Family.telegram_chat_id == chat_id)
                )
                existing_family = existing.scalar_one_or_none()
                if existing_family is not None:
                    logger.info("FAMILY_CONTEXT_FOUND chat_id=%s", chat_id)
                    return existing_family
                continue

            await session.refresh(family)
            logger.info("FAMILY_CREATED family_id=%s chat_id=%s", family.id, chat_id)
            return family

    raise RuntimeError("Unable to create a unique family context.")
