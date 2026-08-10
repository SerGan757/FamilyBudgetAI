from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Float, String, cast, func, literal, select, union_all

from app.database.db import SessionLocal
from app.database.models import GoalContribution, Project, SavingsGoal, Transaction, User


@dataclass
class DisplayOperation:
    kind: str
    id: int
    created_at: datetime
    amount: float
    title: str
    user_name: str
    type: str
    category: str | None = None
    is_recurring: bool = False
    project_name: str | None = None


def _feed_query(family_id: int, start=None, end=None):
    transactions = select(
        literal("transaction").label("kind"), Transaction.id.label("id"),
        Transaction.created_at.label("created_at"), Transaction.amount.label("amount"),
        Transaction.title.label("title"), User.name.label("user_name"),
        Transaction.type.label("type"), Transaction.category.label("category"),
        Transaction.is_recurring.label("is_recurring"), Project.name.label("project_name"),
    ).join(User, User.id == Transaction.user_id).outerjoin(
        Project, (Project.id == Transaction.project_id) & (Project.family_id == family_id),
    ).where(Transaction.family_id == family_id)
    contributions = select(
        literal("goal_contribution").label("kind"), GoalContribution.id.label("id"),
        GoalContribution.created_at.label("created_at"), GoalContribution.amount.label("amount"),
        SavingsGoal.name.label("title"), User.name.label("user_name"),
        literal("goal_contribution").label("type"),
        cast(literal(None), String).label("category"), literal(False).label("is_recurring"),
        cast(literal(None), String).label("project_name"),
    ).join(SavingsGoal, SavingsGoal.id == GoalContribution.goal_id).join(
        User, User.id == GoalContribution.user_id,
    ).where(
        GoalContribution.family_id == family_id,
        SavingsGoal.family_id == family_id,
        User.family_id == family_id,
    )
    if start is not None:
        transactions = transactions.where(Transaction.created_at >= start)
        contributions = contributions.where(GoalContribution.created_at >= start)
    if end is not None:
        transactions = transactions.where(Transaction.created_at < end)
        contributions = contributions.where(GoalContribution.created_at < end)
    return union_all(transactions, contributions).subquery()


async def get_display_feed(family_id: int, *, start=None, end=None, offset=0, limit=20):
    feed = _feed_query(family_id, start, end)
    async with SessionLocal() as session:
        total = int(await session.scalar(select(func.count()).select_from(feed)) or 0)
        goal_total = float(await session.scalar(select(func.coalesce(func.sum(feed.c.amount), 0)).where(
            feed.c.kind == "goal_contribution",
        )) or 0)
        rows = (await session.execute(select(feed).order_by(
            feed.c.created_at.desc(), feed.c.id.desc(),
        ).offset(offset).limit(limit))).mappings().all()
    operations = [DisplayOperation(
        kind=row["kind"], id=row["id"],
        created_at=row["created_at"], amount=float(row["amount"]), title=row["title"],
        user_name=row["user_name"], type=row["type"], category=row["category"],
        is_recurring=bool(row["is_recurring"]), project_name=row["project_name"],
    ) for row in rows]
    return operations, total, goal_total
