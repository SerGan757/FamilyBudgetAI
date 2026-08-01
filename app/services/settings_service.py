from sqlalchemy import func, select

from app.database.db import SessionLocal
from app.database.models import Family, RecurringPayment, Transaction, User


async def get_family_settings_data(family_id: int):
    """Return aggregates for only the current user's family."""
    async with SessionLocal() as session:
        family = await session.get(Family, family_id)
        if family is None:
            return None

        members = await session.execute(
            select(func.count(User.id)).where(User.family_id == family.id)
        )
        transactions = await session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.family_id == family.id
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


async def get_family_members(family_id: int):
    """Return only users belonging to the current user's family."""
    async with SessionLocal() as session:
        members = await session.execute(
            select(User)
            .where(User.family_id == family_id)
            .order_by(User.name, User.id)
        )
        return members.scalars().all()
