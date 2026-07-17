import random
import string

from sqlalchemy import select

from app.database.db import SessionLocal
from app.database.models import Family, User


def generate_invite_code(length: int = 6) -> str:
    return "".join(
        random.choices(
            string.ascii_uppercase + string.digits,
            k=length,
        )
    )


async def get_user_by_telegram_id(telegram_id: int):

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

        family = Family(
            name=f"Семья {name}",
            invite_code=generate_invite_code(),
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