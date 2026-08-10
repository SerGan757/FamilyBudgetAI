from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import contains_eager

from app.database.db import SessionLocal
from app.database.models import Project, Transaction, User
from app.services.financial_feed_service import get_display_feed


def _family_scope(family_id: int):
    return Transaction.family_id == family_id


async def get_transactions_count(family_id: int):
    _, total, _ = await get_display_feed(family_id, limit=0)
    return total


async def get_last_transactions(
    family_id: int,
    limit: int = 20,
    offset: int = 0,
):

    operations, _, _ = await get_display_feed(
        family_id, limit=limit, offset=offset,
    )
    return operations


async def get_transactions_by_category(
    family_id: int,
    category: str,
    limit: int = 20,
    offset: int = 0,
):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction, User)
            .join(
                User,
                Transaction.user_id == User.id,
            )
            .outerjoin(
                Project,
                and_(Project.id == Transaction.project_id, Project.family_id == family_id),
            )
            .options(contains_eager(Transaction.project))
            .where(
                Transaction.family_id == family_id,
                Transaction.category == category
            )
            .order_by(
                desc(Transaction.id)
            )
            .offset(offset)
            .limit(limit)
        )

        rows = result.all()

        transactions = []

        for transaction, user in rows:

            transaction.user_name = user.name

            transactions.append(transaction)

        return transactions


async def get_transactions_by_type(
    family_id: int,
    transaction_type: str,
    limit: int = 20,
    offset: int = 0,
):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction, User)
            .join(
                User,
                Transaction.user_id == User.id,
            )
            .outerjoin(
                Project,
                and_(Project.id == Transaction.project_id, Project.family_id == family_id),
            )
            .options(contains_eager(Transaction.project))
            .where(
                Transaction.family_id == family_id,
                Transaction.type == transaction_type
            )
            .order_by(
                desc(Transaction.id)
            )
            .offset(offset)
            .limit(limit)
        )

        rows = result.all()

        transactions = []

        for transaction, user in rows:

            transaction.user_name = user.name

            transactions.append(transaction)

        return transactions
