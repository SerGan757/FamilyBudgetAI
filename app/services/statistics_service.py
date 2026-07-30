from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from app.database.db import SessionLocal
from app.database.models import Transaction, User
from sqlalchemy.orm import selectinload


def _month_bounds() -> tuple[datetime, datetime]:
    today = date.today()
    month_start = datetime(today.year, today.month, 1)
    if today.month == 12:
        return month_start, datetime(today.year + 1, 1, 1)
    return month_start, datetime(today.year, today.month + 1, 1)


async def _sum(
    family_id: int,
    transaction_type: str,
    start=None,
    end=None,
    recurring: bool | None = None,
):

    async with SessionLocal() as session:

        query = (
            select(Transaction)
            .where(
                Transaction.user.has(User.family_id == family_id),
                Transaction.type == transaction_type
            )
        )

        if start is not None:
            query = query.where(
                Transaction.created_at >= start
            )

        if end is not None:
            query = query.where(
                Transaction.created_at < end
            )

        if recurring is True:
            query = query.where(
                Transaction.is_recurring.is_(True)
            )

        elif recurring is False:
            query = query.where(
                Transaction.is_recurring.is_(False)
            )

        result = await session.execute(query)

        transactions = result.scalars().all()

        return float(
            sum(
                transaction.amount
                for transaction in transactions
            )
        )

async def get_today_statistics(
    family_id: int,
    offset: int = 0,
    limit: int = 20,
):

    today = datetime.combine(
        date.today(),
        datetime.min.time(),
    )

    tomorrow = today + timedelta(days=1)

    income = await _sum(
        family_id,
        "income",
        today,
        tomorrow,
    )

    expense = await _sum(
        family_id,
        "expense",
        today,
        tomorrow,
    )

    recurring = await _sum(
        family_id,
        "expense",
        today,
        tomorrow,
        recurring=True,
    )

    async with SessionLocal() as session:

        count_result = await session.execute(
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.user.has(User.family_id == family_id),
                Transaction.created_at >= today,
                Transaction.created_at < tomorrow,
            )
        )

        total = count_result.scalar() or 0

        recurring_count_result = await session.execute(
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.user.has(User.family_id == family_id),
                Transaction.created_at >= today,
                Transaction.created_at < tomorrow,
                Transaction.is_recurring.is_(True),
            )
        )
        recurring_count = recurring_count_result.scalar() or 0

        result = await session.execute(
            select(Transaction)
            .options(
                selectinload(Transaction.user)
            )
            .where(
                Transaction.user.has(User.family_id == family_id),
                Transaction.created_at >= today,
                Transaction.created_at < tomorrow,
            )
            .order_by(
                Transaction.created_at.desc(),
                Transaction.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        transactions = result.unique().scalars().all()

        return {
            "income": income,
            "expense": expense,
            "recurring": recurring,
            "recurring_count": recurring_count,
            "balance": income - expense,
            "transactions": transactions,
            "total": total,
        }
    

async def get_month_statistics(
    family_id: int,
    year: int | None = None,
    month: int | None = None,
    offset: int = 0,
    limit: int = 20,
):

    today = date.today()
    year = year or today.year
    month = month or today.month
    month_start = datetime(
        year,
        month,
        1,
    )

    if month == 12:
        next_month = datetime(
            year + 1,
            1,
            1,
        )
    else:
        next_month = datetime(
            year,
            month + 1,
            1,
        )

    ordinary_income = await _sum(family_id, "income", month_start, next_month, recurring=False)
    ordinary_expense = await _sum(family_id, "expense", month_start, next_month, recurring=False)
    recurring_income = await _sum(family_id, "income", month_start, next_month, recurring=True)
    recurring_expense = await _sum(family_id, "expense", month_start, next_month, recurring=True)

    async with SessionLocal() as session:
        count_result = await session.execute(
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.user.has(User.family_id == family_id),
                Transaction.created_at >= month_start,
                Transaction.created_at < next_month,
            )
        )

        total = count_result.scalar() or 0

        recurring_income_count_result = await session.execute(
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.user.has(User.family_id == family_id),
                Transaction.created_at >= month_start,
                Transaction.created_at < next_month,
                Transaction.is_recurring.is_(True),
                Transaction.type == "income",
            )
        )
        recurring_income_count = recurring_income_count_result.scalar() or 0
        recurring_expense_count_result = await session.execute(
            select(func.count()).select_from(Transaction).where(
                Transaction.user.has(User.family_id == family_id),
                Transaction.created_at >= month_start,
                Transaction.created_at < next_month,
                Transaction.is_recurring.is_(True),
                Transaction.type == "expense",
            )
        )
        recurring_expense_count = recurring_expense_count_result.scalar() or 0

        result = await session.execute(
            select(Transaction)
            .options(
                selectinload(Transaction.user)
            )
            .where(
                Transaction.user.has(User.family_id == family_id),
                Transaction.created_at >= month_start,
                Transaction.created_at < next_month,
            )
            .order_by(
                Transaction.created_at.desc(),
                Transaction.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        transactions = result.unique().scalars().all()

    return {
        "ordinary_income": ordinary_income,
        "ordinary_expense": ordinary_expense,
        "recurring_income": recurring_income,
        "recurring_expense": recurring_expense,
        "recurring_income_count": recurring_income_count,
        "recurring_expense_count": recurring_expense_count,
        "balance": ordinary_income + recurring_income - ordinary_expense - recurring_expense,
        "transactions": transactions,
        "total": total,
    }

def build_balance_data(transactions):
    """Split actual monthly transactions without counting recurring rows twice."""
    data = {
        "ordinary_income": 0.0, "ordinary_expense": 0.0,
        "recurring_income": 0.0, "recurring_expense": 0.0,
        "recurring_income_count": 0, "recurring_expense_count": 0,
    }
    for transaction in transactions:
        if transaction.type == "income":
            key = "recurring_income" if transaction.is_recurring else "ordinary_income"
        else:
            key = "recurring_expense" if transaction.is_recurring else "ordinary_expense"
        data[key] += transaction.amount
        if transaction.is_recurring:
            data[f"{key}_count"] += 1
    data["balance"] = (
        data["ordinary_income"] + data["recurring_income"]
        - data["ordinary_expense"] - data["recurring_expense"]
    )
    return data


async def get_balance(family_id: int):
    month_start, next_month = _month_bounds()
    async with SessionLocal() as session:
        result = await session.execute(
            select(Transaction).where(
                Transaction.user.has(User.family_id == family_id),
                Transaction.created_at >= month_start,
                Transaction.created_at < next_month,
            )
        )
        return build_balance_data(result.scalars().all())


async def get_category_statistics():

    async with SessionLocal() as session:

        result = await session.execute(
            select(
                Transaction.category,
                func.sum(Transaction.amount),
            )
            .where(
                Transaction.type == "expense"
            )
            .group_by(
                Transaction.category,
            )
            .order_by(
                func.sum(Transaction.amount).desc()
            )
        )

        return result.all()

        # =====================================================
# ANALYTICS
# =====================================================

async def get_month_transactions(family_id: int):

    today = date.today()

    month_start = datetime(
        today.year,
        today.month,
        1,
    )

    if today.month == 12:
        next_month = datetime(
            today.year + 1,
            1,
            1,
        )
    else:
        next_month = datetime(
            today.year,
            today.month + 1,
            1,
        )

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction)
            .options(
                selectinload(Transaction.user)
            )
            .where(
                Transaction.user.has(User.family_id == family_id),
                Transaction.created_at >= month_start,
                Transaction.created_at < next_month,
            )
            .order_by(
                Transaction.created_at.desc()
            )
        )

        return result.unique().scalars().all()


async def get_users_statistics(family_id: int):

    transactions = await get_month_transactions(family_id)

    users = {}

    for t in transactions:

        if t.type != "expense":
            continue

        if t.is_recurring:
            continue

        name = (
            t.user.name
            if t.user
            else "Неизвестно"
        )

        users[name] = (
            users.get(name, 0)
            + t.amount
        )

    return sorted(
        users.items(),
        key=lambda x: x[1],
        reverse=True,
    )


async def get_categories_statistics(family_id: int):

    transactions = await get_month_transactions(family_id)

    categories = {}

    for t in transactions:

        if t.type != "expense":
            continue

        if t.is_recurring:
            continue

        categories[t.category] = (
            categories.get(
                t.category,
                0,
            )
            + t.amount
        )

    return sorted(
        categories.items(),
        key=lambda x: x[1],
        reverse=True,
    )


async def get_biggest_purchase(family_id: int):

    transactions = await get_month_transactions(family_id)

    expense = [
        t
        for t in transactions
        if (
            t.type == "expense"
            and not t.is_recurring
        )
    ]

    if not expense:
        return None

    return max(
        expense,
        key=lambda x: x.amount,
    )


async def get_average_check(family_id: int):

    transactions = await get_month_transactions(family_id)

    expenses = [
        t.amount
        for t in transactions
        if (
            t.type == "expense"
            and not t.is_recurring
        )
    ]

    if not expenses:
        return 0

    return round(
        sum(expenses) / len(expenses),
        2,
    )


async def get_average_day_expense(family_id: int):

    transactions = await get_month_transactions(family_id)

    by_day = {}

    for t in transactions:

        if t.type != "expense":
            continue

        if t.is_recurring:
            continue

        day = t.created_at.date()

        by_day[day] = (
            by_day.get(day, 0)
            + t.amount
        )

    if not by_day:
        return 0

    return round(
        sum(by_day.values()) / len(by_day),
        2,
    )


async def get_month_operations(family_id: int):

    transactions = await get_month_transactions(family_id)

    return len(transactions)


async def get_analytics(family_id: int):

    stats = await get_month_statistics(family_id)

    users = await get_users_statistics(family_id)

    categories = await get_categories_statistics(family_id)

    biggest = await get_biggest_purchase(family_id)

    average_check = await get_average_check(family_id)

    average_day = await get_average_day_expense(family_id)

    operations = await get_month_operations(family_id)

    return {

        "income": stats["income"],

        "expense": stats["expense"],

        "recurring": stats["recurring"],

        "balance": stats["balance"],

        "recurring_count": stats["recurring_count"],

        "users": users,

        "categories": categories,

        "biggest": biggest,

        "average_check": average_check,

        "average_day": average_day,

        "operations": operations,

    }
