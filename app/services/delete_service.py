from dataclasses import dataclass

from sqlalchemy import desc, select

from app.database.db import SessionLocal
from app.database.models import GoalContribution, SavingsGoal, Transaction
from app.services.family_activity_service import touch_family_activity


@dataclass
class DeletedOperation:
    id: int
    title: str
    amount: float
    type: str


async def delete_transactions_by_ids(ids: list[int], family_id: int):

    deleted = []

    for transaction_id in ids:

        transaction = await delete_operation_by_id(
            transaction_id, family_id
        )

        if transaction:
            deleted.append(transaction)

    return deleted


async def delete_operation_by_id(operation_id: int, family_id: int):
    async with SessionLocal() as session:
        transaction = await session.scalar(select(Transaction).where(
            Transaction.id == operation_id,
            Transaction.family_id == family_id,
        ))
        if transaction is not None:
            deleted = DeletedOperation(
                id=transaction.id, title=transaction.title,
                amount=transaction.amount, type=transaction.type,
            )
            await session.delete(transaction)
            await touch_family_activity(family_id, session=session)
            await session.commit()
            return deleted

        result = await session.execute(select(GoalContribution, SavingsGoal.name).join(
            SavingsGoal, SavingsGoal.id == GoalContribution.goal_id,
        ).where(
            GoalContribution.id == operation_id,
            GoalContribution.family_id == family_id,
            SavingsGoal.family_id == family_id,
        ))
        row = result.one_or_none()
        contribution, goal_name = row if row is not None else (None, None)
        if contribution is None:
            return None

        deleted = DeletedOperation(
            id=contribution.id, title=goal_name,
            amount=contribution.amount, type="goal_contribution",
        )
        await session.delete(contribution)
        await touch_family_activity(family_id, session=session)
        await session.commit()
        return deleted

async def delete_last_transaction(family_id: int):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction).where(Transaction.family_id == family_id)
            .order_by(desc(Transaction.id))
            .limit(1)
        )

        transaction = result.scalar_one_or_none()

        if transaction is None:
            return None

        await session.delete(transaction)
        await touch_family_activity(family_id, session=session)
        await session.commit()

        return transaction


async def delete_transaction_by_id(transaction_id: int, family_id: int):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction).where(
                Transaction.id == transaction_id,
                Transaction.family_id == family_id,
            )
        )

        transaction = result.scalar_one_or_none()

        if transaction is None:
            return None

        await session.delete(transaction)
        await touch_family_activity(family_id, session=session)
        await session.commit()

        return transaction
