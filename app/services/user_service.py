from sqlalchemy import select

from app.database.db import SessionLocal
from app.database.models import User
from app.services.family_activity_service import touch_family_activity


async def get_user_by_telegram_id(telegram_id: int):
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


async def create_user(
    telegram_id: int,
    name: str,
    family_id: int,
):
    """Create a user in the explicitly selected chat family."""
    async with SessionLocal() as session:
        user = User(
            telegram_id=telegram_id,
            name=name,
            family_id=family_id,
        )
        session.add(user)
        await touch_family_activity(family_id, session=session)
        await session.commit()
        await session.refresh(user)
        return user
