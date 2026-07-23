from sqlalchemy import select

from app.database.db import SessionLocal
from app.database.models import Family, User


async def get_family():

    async with SessionLocal() as session:

        result = await session.execute(
            select(Family)
        )

        family = result.scalar_one_or_none()

        if family:
            return family

        family = Family(
            name="Family",
            invite_code="FAMILY",
        )

        session.add(family)

        await session.commit()

        await session.refresh(family)

        return family


async def get_user_by_telegram_id(
    telegram_id: int,
):

    async with SessionLocal() as session:

        result = await session.execute(
            select(User).where(
                User.telegram_id == telegram_id
            )
        )

        return result.scalar_one_or_none()


async def create_user(
    telegram_id: int,
    name: str,
):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Family)
        )

        family = result.scalar_one_or_none()

        if family is None:

            family = Family(
                name="Family",
                invite_code="FAMILY",
            )

            session.add(family)

            await session.flush()

        user = User(
            telegram_id=telegram_id,
            name=name,
            family_id=family.id,
        )

        session.add(user)

        await session.commit()

        await session.refresh(user)

        return user