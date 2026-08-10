import calendar
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.database.db import SessionLocal
from app.database.models import GoalContribution, SavingsGoal, User

MIN_SAVINGS_OBSERVATION_DAYS = 7


@dataclass(frozen=True)
class GoalSnapshot:
    goal: SavingsGoal
    saved: float
    remaining: float
    percentage: float
    month_contributions: float = 0.0
    average_per_day: float | None = None
    expected_date: date | None = None
    days_to_goal: int | None = None
    required_per_month: float | None = None
    current_per_month: float | None = None
    pace_difference: float | None = None
    schedule_months: int | None = None


def progress_bar(saved: float, target: float, segments: int = 10) -> str:
    percentage = 0.0 if target <= 0 else max(0.0, saved / target * 100)
    filled = min(segments, max(0, round(min(percentage, 100) / 100 * segments)))
    return f"{'█' * filled}{'░' * (segments - filled)} {percentage:.0f}%"


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end


def _remaining_months(today: date, deadline: date) -> float:
    if deadline <= today:
        return 0.0
    days = (deadline - today).days
    return max(days / (365.2425 / 12), 1 / (365.2425 / 12))


def calculate_observed_pace(first_date: date | None, today: date, recent_amount: float, remaining: float):
    if first_date is None or (today - first_date).days < MIN_SAVINGS_OBSERVATION_DAYS or recent_amount <= 0:
        return None, None, None, None
    observed_days = min(30, (today - first_date).days + 1)
    average = recent_amount / observed_days
    days_to_goal = math.ceil(remaining / average) if remaining > 0 else 0
    expected = today + timedelta(days=days_to_goal)
    return average, days_to_goal, expected, average * (365.2425 / 12)


async def get_active_goal(family_id: int):
    async with SessionLocal() as session:
        return await session.scalar(select(SavingsGoal).where(
            SavingsGoal.family_id == family_id, SavingsGoal.is_active.is_(True),
        ))


async def create_goal(family_id: int, name: str, target_amount: float, deadline: date | None = None):
    name = name.strip()
    if not name or len(name) > 100 or target_amount <= 0:
        raise ValueError("invalid goal")
    async with SessionLocal() as session:
        existing = await session.scalar(select(SavingsGoal.id).where(
            SavingsGoal.family_id == family_id, SavingsGoal.is_active.is_(True),
        ))
        if existing is not None:
            raise ValueError("active goal already exists")
        goal = SavingsGoal(
            family_id=family_id, name=name, target_amount=target_amount, deadline=deadline,
        )
        session.add(goal)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise ValueError("active goal already exists") from exc
        await session.refresh(goal)
        return goal


async def update_goal(family_id: int, goal_id: int, name: str, target_amount: float, deadline: date | None):
    async with SessionLocal() as session:
        goal = await session.scalar(select(SavingsGoal).where(
            SavingsGoal.id == goal_id, SavingsGoal.family_id == family_id,
            SavingsGoal.is_active.is_(True),
        ))
        if goal is None:
            return None
        if not name.strip() or len(name.strip()) > 100 or target_amount <= 0:
            raise ValueError("invalid goal")
        goal.name, goal.target_amount, goal.deadline = name.strip(), target_amount, deadline
        await session.commit()
        return goal


async def add_contribution(family_id: int, telegram_id: int, amount: float):
    if amount <= 0 or not math.isfinite(amount):
        raise ValueError("invalid contribution")
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(
            User.telegram_id == telegram_id, User.family_id == family_id,
        ))
        goal = await session.scalar(select(SavingsGoal).where(
            SavingsGoal.family_id == family_id, SavingsGoal.is_active.is_(True),
        ))
        if user is None or goal is None:
            return None
        contribution = GoalContribution(
            goal_id=goal.id, family_id=family_id, user_id=user.id, amount=amount,
        )
        session.add(contribution)
        await session.commit()
        await session.refresh(contribution)
        return contribution


async def complete_goal(family_id: int, goal_id: int) -> bool:
    async with SessionLocal() as session:
        goal = await session.scalar(select(SavingsGoal).where(
            SavingsGoal.id == goal_id, SavingsGoal.family_id == family_id,
            SavingsGoal.is_active.is_(True),
        ))
        if goal is None:
            return False
        goal.is_active, goal.completed_at = False, datetime.utcnow()
        await session.commit()
        return True


async def delete_goal(family_id: int, goal_id: int) -> bool:
    async with SessionLocal() as session:
        goal = await session.scalar(select(SavingsGoal).where(
            SavingsGoal.id == goal_id, SavingsGoal.family_id == family_id,
        ))
        if goal is None:
            return False
        await session.delete(goal)
        await session.commit()
        return True


async def delete_contribution(family_id: int, contribution_id: int) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(delete(GoalContribution).where(
            GoalContribution.id == contribution_id,
            GoalContribution.family_id == family_id,
        ))
        await session.commit()
        return bool(result.rowcount)


async def delete_last_contribution(family_id: int, goal_id: int) -> bool:
    async with SessionLocal() as session:
        contribution = await session.scalar(select(GoalContribution).where(
            GoalContribution.family_id == family_id,
            GoalContribution.goal_id == goal_id,
        ).order_by(GoalContribution.created_at.desc(), GoalContribution.id.desc()).limit(1))
        if contribution is None:
            return False
        await session.delete(contribution)
        await session.commit()
        return True


async def get_goal_snapshot(family_id: int, year: int | None = None, month: int | None = None, today: date | None = None):
    today = today or date.today()
    year, month = year or today.year, month or today.month
    start, end = _month_bounds(year, month)
    async with SessionLocal() as session:
        goal = await session.scalar(select(SavingsGoal).where(
            SavingsGoal.family_id == family_id, SavingsGoal.is_active.is_(True),
        ))
        if goal is None:
            return None
        saved = float(await session.scalar(select(func.coalesce(func.sum(GoalContribution.amount), 0)).where(
            GoalContribution.goal_id == goal.id, GoalContribution.family_id == family_id,
        )) or 0)
        month_saved = float(await session.scalar(select(func.coalesce(func.sum(GoalContribution.amount), 0)).where(
            GoalContribution.goal_id == goal.id, GoalContribution.family_id == family_id,
            GoalContribution.created_at >= start, GoalContribution.created_at < end,
        )) or 0)
        first = await session.scalar(select(func.min(GoalContribution.created_at)).where(
            GoalContribution.goal_id == goal.id, GoalContribution.family_id == family_id,
        ))
        recent_start = datetime.combine(today - timedelta(days=29), datetime.min.time())
        recent = float(await session.scalar(select(func.coalesce(func.sum(GoalContribution.amount), 0)).where(
            GoalContribution.goal_id == goal.id, GoalContribution.family_id == family_id,
            GoalContribution.created_at >= recent_start,
        )) or 0)

    remaining = max(goal.target_amount - saved, 0.0)
    percentage = 0 if goal.target_amount <= 0 else saved / goal.target_amount * 100
    average, days_to_goal, expected, current_monthly = calculate_observed_pace(
        first.date() if first is not None else None, today, recent, remaining,
    )
    required = None
    pace = None
    schedule = None
    if goal.deadline:
        months_left = _remaining_months(today, goal.deadline)
        required = remaining / months_left if months_left > 0 else remaining
        if current_monthly is not None:
            pace = current_monthly - required
        if expected:
            schedule = round((expected - goal.deadline).days / (365.2425 / 12))
    return GoalSnapshot(
        goal=goal, saved=saved, remaining=remaining, percentage=percentage,
        month_contributions=month_saved, average_per_day=average,
        expected_date=expected, days_to_goal=days_to_goal,
        required_per_month=required, current_per_month=current_monthly,
        pace_difference=pace, schedule_months=schedule,
    )
