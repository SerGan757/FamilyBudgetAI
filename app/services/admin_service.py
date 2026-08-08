import os
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select, text

from app.database.db import SessionLocal
from app.database.models import Family, RecurringPayment, Transaction, User
from app.services.statistics_service import get_month_statistics


def _current_year_month() -> tuple[int, int]:
    timezone_name = os.getenv("TIMEZONE", "Europe/Berlin")
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo("Europe/Berlin")
    now = datetime.now(timezone)
    return now.year, now.month


def _month_bounds() -> tuple[datetime, datetime]:
    year, month = _current_year_month()
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end


async def get_admin_status() -> dict[str, int | str]:
    async with SessionLocal() as session:
        database_name = (await session.execute(text("SELECT current_database()"))).scalar_one()
        counts = {}
        for name, model in (
            ("families", Family), ("users", User), ("transactions", Transaction),
            ("recurring_payments", RecurringPayment),
        ):
            counts[name] = (await session.execute(select(func.count()).select_from(model))).scalar_one()
    return {"database": database_name, **counts}


async def get_admin_families_page(page: int, page_size: int) -> tuple[list[tuple[int, str]], int]:
    async with SessionLocal() as session:
        total = (await session.execute(select(func.count()).select_from(Family))).scalar_one()
        rows = await session.execute(
            select(Family.id, Family.name).order_by(Family.id).offset(page * page_size).limit(page_size)
        )
        return [(row.id, row.name) for row in rows], total


async def get_admin_family(family_id: int) -> dict[str, object] | None:
    async with SessionLocal() as session:
        family = await session.get(Family, family_id)
        if family is None:
            return None
        users = (await session.execute(
            select(func.count()).select_from(User).where(User.family_id == family_id)
        )).scalar_one()
        transactions = (await session.execute(
            select(func.count()).select_from(Transaction).where(Transaction.family_id == family_id)
        )).scalar_one()
        recurring = (await session.execute(
            select(func.count()).select_from(RecurringPayment).where(RecurringPayment.family_id == family_id)
        )).scalar_one()
        thirty_days_ago = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
        recent_transactions = (await session.execute(
            select(func.count()).select_from(Transaction).where(
                Transaction.family_id == family_id,
                Transaction.created_at >= thirty_days_ago,
            )
        )).scalar_one()
        return {
            "id": family.id, "name": family.name, "users": users,
            "created_at": family.created_at,
            "last_activity_at": family.last_activity_at,
            "country": family.country,
            "city": family.city,
            "language": family.language,
            "timezone": family.timezone,
            "currency": family.currency,
            "is_active": family.is_active,
            "plan": family.plan,
            "paid_until": family.paid_until,
            "trial_until": family.trial_until,
            "last_payment_at": family.last_payment_at,
            "disabled_reason": family.disabled_reason,
            "transactions": transactions,
            "recurring_payments": recurring,
            "transactions_30_days": recent_transactions,
        }


async def get_admin_family_members(family_id: int) -> tuple[str, list[str]] | None:
    async with SessionLocal() as session:
        family = await session.get(Family, family_id)
        if family is None:
            return None
        names = (await session.execute(
            select(User.name).where(User.family_id == family_id).order_by(User.id)
        )).scalars().all()
        return family.name, list(names)


async def get_admin_family_statistics(family_id: int) -> dict[str, int | float | str] | None:
    async with SessionLocal() as session:
        family = await session.get(Family, family_id)
        if family is None:
            return None
        family_name = family.name
    year, month = _current_year_month()
    stats = await get_month_statistics(family_id, year=year, month=month, limit=1)
    income = stats["ordinary_income"] + stats["recurring_income"]
    expense = stats["ordinary_expense"] + stats["recurring_expense"]
    return {
        "name": family_name, "income": income, "expense": expense,
        "balance": income - expense, "operations": stats["total"],
        "recurring_income": stats["recurring_income"],
        "recurring_expense": stats["recurring_expense"],
    }


async def get_admin_users_page(page: int, page_size: int) -> tuple[list[tuple[int, str]], int]:
    async with SessionLocal() as session:
        total = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        rows = await session.execute(
            select(User.id, User.name).order_by(User.id).offset(page * page_size).limit(page_size)
        )
        return [(row.id, row.name) for row in rows], total


async def get_admin_user(user_id: int) -> dict[str, int | float | str] | None:
    start, end = _month_bounds()
    async with SessionLocal() as session:
        row = (await session.execute(
            select(User.id, User.name, User.family_id, Family.name.label("family_name"))
            .join(Family, Family.id == User.family_id)
            .where(User.id == user_id)
        )).one_or_none()
        if row is None:
            return None
        aggregates = (await session.execute(
            select(
                func.count(Transaction.id).label("operations"),
                func.coalesce(func.sum(Transaction.amount).filter(Transaction.type == "income"), 0).label("income"),
                func.coalesce(func.sum(Transaction.amount).filter(Transaction.type == "expense"), 0).label("expense"),
            ).where(
                Transaction.user_id == user_id,
                Transaction.created_at >= start,
                Transaction.created_at < end,
            )
        )).one()
        return {
            "id": row.id, "name": row.name, "family_id": row.family_id,
            "family_name": row.family_name, "operations": aggregates.operations,
            "income": float(aggregates.income), "expense": float(aggregates.expense),
        }
