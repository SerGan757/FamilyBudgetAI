from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import case, extract, func, select

from app.database.db import SessionLocal
from app.database.models import (
    FamilyCategory, GoalContribution, RecurringPayment, SavingsGoal, Transaction, User,
)


@dataclass(frozen=True)
class YearMonth:
    month: int
    income: float = 0.0
    expense: float = 0.0
    goals: float = 0.0

    @property
    def result(self):
        return self.income - self.expense - self.goals


@dataclass(frozen=True)
class YearAnalytics:
    year: int
    months: tuple[YearMonth, ...]
    categories: tuple[tuple[str, float, int | None], ...]
    members: tuple[tuple[str, float], ...]
    goals: tuple[tuple[str, float], ...]
    income: float
    expense: float
    goal_contributions: float
    recurring_income_load: float
    recurring_expense_load: float
    recurring_actual_income: float
    recurring_actual_expense: float
    income_sources: tuple[tuple[str, float], ...] = ()

    @property
    def months_with_data(self): return len(self.months)
    @property
    def financial_result(self): return self.income - self.expense - self.goal_contributions
    @property
    def average_income(self): return self.income / self.months_with_data if self.months_with_data else 0.0
    @property
    def average_expense(self): return self.expense / self.months_with_data if self.months_with_data else 0.0
    @property
    def average_goals(self): return self.goal_contributions / self.months_with_data if self.months_with_data else 0.0
    @property
    def best_income_month(self): return max(self.months, key=lambda row: row.income, default=None)
    @property
    def highest_expense_month(self): return max(self.months, key=lambda row: row.expense, default=None)
    @property
    def best_result_month(self): return max(self.months, key=lambda row: row.result, default=None)
    @property
    def worst_result_month(self): return min(self.months, key=lambda row: row.result, default=None)


def safe_timezone(timezone_name: str):
    try: return ZoneInfo(timezone_name or "Europe/Berlin")
    except ZoneInfoNotFoundError: return ZoneInfo("Europe/Berlin")


def year_bounds(year: int, timezone_name: str):
    zone = safe_timezone(timezone_name)
    start = datetime(year, 1, 1, tzinfo=zone).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    end = datetime(year + 1, 1, 1, tzinfo=zone).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return start, end


def year_expense_categories_statement(family_id: int, start: datetime, end: datetime):
    expense_amount = func.coalesce(func.sum(case(
        (Transaction.type == "expense", Transaction.amount), else_=0,
    )), 0)
    return (select(
        Transaction.category, Transaction.custom_category_id,
        FamilyCategory.icon, FamilyCategory.name, expense_amount,
    ).outerjoin(FamilyCategory, FamilyCategory.id == Transaction.custom_category_id)
      .where(Transaction.family_id == family_id, Transaction.created_at >= start, Transaction.created_at < end)
      .group_by(Transaction.category, Transaction.custom_category_id, FamilyCategory.icon, FamilyCategory.name)
      .having(expense_amount > 0)
      .order_by(expense_amount.desc()))


def normalized_income_title():
    return func.lower(func.trim(func.regexp_replace(Transaction.title, r"\s+", " ", "g")))


def year_income_sources_statement(family_id: int, start: datetime, end: datetime):
    normalized_title = normalized_income_title().label("normalized_title")
    total = func.sum(Transaction.amount).label("total")
    return (select(normalized_title, func.min(func.trim(Transaction.title)), total)
      .where(
          Transaction.family_id == family_id,
          Transaction.type == "income",
          Transaction.created_at >= start,
          Transaction.created_at < end,
      )
      .group_by(normalized_title)
      .order_by(total.desc()))


async def get_year_analytics(family_id: int, year: int, timezone_name="Europe/Berlin"):
    start, end = year_bounds(year, timezone_name)
    timezone_name = safe_timezone(timezone_name).key
    tx_local_time = func.timezone(timezone_name, func.timezone("UTC", Transaction.created_at))
    goal_local_time = func.timezone(timezone_name, func.timezone("UTC", GoalContribution.created_at))
    async with SessionLocal() as session:
        tx_months = (await session.execute(select(
            extract("month", tx_local_time).label("month"),
            func.coalesce(func.sum(case((Transaction.type == "income", Transaction.amount), else_=0)), 0),
            func.coalesce(func.sum(case((Transaction.type == "expense", Transaction.amount), else_=0)), 0),
        ).where(Transaction.family_id == family_id, Transaction.created_at >= start, Transaction.created_at < end)
          .group_by("month").order_by("month"))).all()
        goal_months = (await session.execute(select(
            extract("month", goal_local_time).label("month"), func.sum(GoalContribution.amount),
        ).where(GoalContribution.family_id == family_id, GoalContribution.created_at >= start, GoalContribution.created_at < end)
          .group_by("month"))).all()
        category_rows = (await session.execute(
            year_expense_categories_statement(family_id, start, end)
        )).all()
        income_source_rows = (await session.execute(
            year_income_sources_statement(family_id, start, end)
        )).all()
        member_rows = (await session.execute(select(User.name, func.sum(Transaction.amount))
          .join(User, User.id == Transaction.user_id)
          .where(Transaction.family_id == family_id, User.family_id == family_id, Transaction.type == "expense", Transaction.created_at >= start, Transaction.created_at < end)
          .group_by(User.id, User.name).order_by(func.sum(Transaction.amount).desc()))).all()
        goal_rows = (await session.execute(select(SavingsGoal.name, func.sum(GoalContribution.amount))
          .join(SavingsGoal, SavingsGoal.id == GoalContribution.goal_id)
          .where(GoalContribution.family_id == family_id, SavingsGoal.family_id == family_id, GoalContribution.created_at >= start, GoalContribution.created_at < end)
          .group_by(SavingsGoal.id, SavingsGoal.name).order_by(func.sum(GoalContribution.amount).desc()))).all()
        load_rows = (await session.execute(select(RecurringPayment.type, func.coalesce(func.sum(RecurringPayment.amount), 0))
          .where(RecurringPayment.family_id == family_id, RecurringPayment.active.is_(True))
          .group_by(RecurringPayment.type))).all()
        actual_rows = (await session.execute(select(Transaction.type, func.coalesce(func.sum(Transaction.amount), 0))
          .where(Transaction.family_id == family_id, Transaction.is_recurring.is_(True), Transaction.created_at >= start, Transaction.created_at < end)
          .group_by(Transaction.type))).all()

    by_month = {int(month): [float(income), float(expense), 0.0] for month, income, expense in tx_months}
    for month, amount in goal_months:
        by_month.setdefault(int(month), [0.0, 0.0, 0.0])[2] = float(amount or 0)
    months = tuple(YearMonth(month, *values) for month, values in sorted(by_month.items()))
    categories = tuple(
        (f"{icon} {name}" if custom_id and name else stored, float(amount), custom_id)
        for stored, custom_id, icon, name, amount in category_rows
    )
    loads = {kind: float(amount) for kind, amount in load_rows}
    actual = {kind: float(amount) for kind, amount in actual_rows}
    return YearAnalytics(
        year, months, categories, tuple((name, float(amount)) for name, amount in member_rows),
        tuple((name, float(amount)) for name, amount in goal_rows),
        sum(row.income for row in months), sum(row.expense for row in months), sum(row.goals for row in months),
        loads.get("income", 0), loads.get("expense", 0), actual.get("income", 0), actual.get("expense", 0),
        tuple((display_title or normalized_title, float(amount)) for normalized_title, display_title, amount in income_source_rows),
    )


async def get_year_category_transactions(family_id, year, timezone_name, *, stored=None, custom_id=None, limit=50):
    start, end = year_bounds(year, timezone_name)
    async with SessionLocal() as session:
        query = select(Transaction, User.name).join(User, User.id == Transaction.user_id).where(
            Transaction.family_id == family_id, User.family_id == family_id,
            Transaction.type == "expense", Transaction.created_at >= start, Transaction.created_at < end,
        )
        query = query.where(Transaction.custom_category_id == custom_id) if custom_id else query.where(Transaction.category == stored)
        rows = (await session.execute(query.order_by(Transaction.created_at.desc(), Transaction.id.desc()).limit(limit))).all()
    return rows
