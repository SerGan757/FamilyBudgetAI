from sqlalchemy import func, select

from app.database.db import SessionLocal
from app.database.models import Family, RecurringPayment, Transaction, User


async def get_family_settings_data(telegram_id: int):
    """Return aggregates for only the current user's family."""
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user is None:
            return None

        family = await session.get(Family, user.family_id)
        if family is None:
            return None

        members = await session.execute(
            select(func.count(User.id)).where(User.family_id == family.id)
        )
        transactions = await session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.user.has(User.family_id == family.id)
            )
        )
        recurring = await session.execute(
            select(func.count(RecurringPayment.id)).where(RecurringPayment.family_id == family.id)
        )
        return {
            "id": family.id,
            "name": family.name,
            "created_at": family.created_at,
            "members_count": members.scalar_one(),
            "transactions_count": transactions.scalar_one(),
            "recurring_count": recurring.scalar_one(),
        }


async def get_family_members(telegram_id: int):
    """Return only users belonging to the current user's family."""
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user is None:
            return None

        members = await session.execute(
            select(User)
            .where(User.family_id == user.family_id)
            .order_by(User.name, User.id)
        )
        return members.scalars().all()
