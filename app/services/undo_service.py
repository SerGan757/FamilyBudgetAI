from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select

from app.database.db import SessionLocal
from app.database.models import GoalContribution, Transaction
from app.services.family_activity_service import touch_family_activity


UNDO_TTL = timedelta(seconds=60)
TRANSACTION_KIND = "transaction"
GOAL_CONTRIBUTION_KIND = "goal"


@dataclass(frozen=True)
class UndoResult:
    status: str
    operation_id: int
    kind: str


async def undo_recent_operation(
    kind: str,
    operation_id: int,
    family_id: int,
    user_id: int,
    *,
    now: datetime | None = None,
) -> UndoResult:
    """Delete one recent operation only when its family and author match."""
    model = {
        TRANSACTION_KIND: Transaction,
        GOAL_CONTRIBUTION_KIND: GoalContribution,
    }.get(kind)
    if model is None:
        return UndoResult("forbidden", operation_id, kind)

    async with SessionLocal() as session:
        operation = await session.scalar(
            select(model).where(model.id == operation_id).with_for_update()
        )
        if operation is None:
            return UndoResult("already_deleted", operation_id, kind)
        if operation.family_id != family_id:
            return UndoResult("forbidden", operation_id, kind)
        if operation.user_id != user_id:
            return UndoResult("not_author", operation_id, kind)
        if kind == TRANSACTION_KIND and operation.is_recurring:
            return UndoResult("forbidden", operation_id, kind)

        current_time = now or datetime.utcnow()
        created_at = operation.created_at
        if created_at is None or current_time - created_at > UNDO_TTL:
            return UndoResult("expired", operation_id, kind)

        await session.delete(operation)
        await touch_family_activity(family_id, session=session)
        await session.commit()
        return UndoResult("deleted", operation_id, kind)
