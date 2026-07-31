from sqlalchemy import select

from app.database.db import SessionLocal
from app.database.models import User


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
        await session.commit()
        await session.refresh(user)
        return user
