from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.db import SessionLocal
from app.database.models import Family


async def touch_family_activity(
    family_id: int,
    *,
    session: AsyncSession | None = None,
) -> None:
    """Record real family activity, optionally inside the caller's transaction."""
    statement = (
        update(Family)
        .where(Family.id == family_id)
        .values(last_activity_at=datetime.now(UTC).replace(tzinfo=None))
    )
    if session is not None:
        await session.execute(statement)
        return

    async with SessionLocal() as own_session:
        await own_session.execute(statement)
        await own_session.commit()
