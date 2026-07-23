from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from app.database.db import SessionLocal
from app.database.models import Transaction
from sqlalchemy.orm import selectinload


async def _sum(
    transaction_type: str,
    start=None,
    end=None,
    recurring: bool | None = None,
):

    async with SessionLocal() as session:

        query = (
            select(Transaction)
            .where(
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

        if recurring:

            unique = {}

            for transaction in transactions:

                key = (
                    transaction.recurring_payment_id
                    or transaction.title
                )

                unique[key] = transaction.amount

            return float(sum(unique.values()))

        return float(
            sum(
                transaction.amount
                for transaction in transactions
            )
        )

async def get_today_statistics():

    today = datetime.combine(
        date.today(),
        datetime.min.time(),
    )

    tomorrow = today + timedelta(days=1)

    income = await _sum(
        "income",
        today,
        tomorrow,
    )

    expense = await _sum(
        "expense",
        today,
        tomorrow,
        recurring=False,
    )

    recurring = await _sum(
        "expense",
        today,
        tomorrow,
        recurring=True,
    )

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction)
            .options(
                selectinload(Transaction.user)
            )
            .where(
                Transaction.created_at >= today,
                Transaction.created_at < tomorrow,
            )
            .order_by(
                Transaction.is_recurring.desc(),
                Transaction.created_at.desc(),
                Transaction.id.desc(),
            )
            .limit(20)
        )

        transactions = result.unique().scalars().all()

    return {
        "income": income,
        "expense": expense,
        "recurring": recurring,
        "recurring_count": len(
            {
                t.recurring_payment_id or t.title
                for t in transactions
                if t.is_recurring
            }
        ),
        "balance": income - expense - recurring,
        "transactions": transactions,
    }

async def get_month_statistics():

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

    income = await _sum(
        "income",
        month_start,
        next_month,
    )

    expense = await _sum(
        "expense",
        month_start,
        next_month,
        recurring=False,
    )

    recurring = await _sum(
        "expense",
        month_start,
        next_month,
        recurring=True,
    )

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction)
            .options(
                selectinload(Transaction.user)
            )
            .where(
                Transaction.created_at >= month_start,
                Transaction.created_at < next_month,
            )
            .order_by(
                Transaction.is_recurring.desc(),
                Transaction.created_at.desc(),
                Transaction.id.desc(),
            )
            .limit(20)
        )

        transactions = result.unique().scalars().all()

    return {
        "income": income,
        "expense": expense,
        "recurring": recurring,
        "recurring_count": len(
            {
                t.recurring_payment_id or t.title
                for t in transactions
                if t.is_recurring
            }
        ),
        "balance": income - expense - recurring,
        "transactions": transactions,
    }

async def get_balance():

    income = await _sum(
        "income",
    )

    expense = await _sum(
        "expense",
        recurring=False,
    )

    recurring = await _sum(
        "expense",
        recurring=True,
    )

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction).where(
                Transaction.is_recurring.is_(True)
            )
        )

        recurring_count = len(result.scalars().all())

    return {
        "income": income,
        "expense": expense,
        "recurring": recurring,
        "recurring_count": recurring_count,
        "balance": income - expense - recurring,
    }


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

async def get_month_transactions():

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
                Transaction.created_at >= month_start,
                Transaction.created_at < next_month,
            )
            .order_by(
                Transaction.created_at.desc()
            )
        )

        return result.unique().scalars().all()


async def get_users_statistics():

    transactions = await get_month_transactions()

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


async def get_categories_statistics():

    transactions = await get_month_transactions()

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


async def get_biggest_purchase():

    transactions = await get_month_transactions()

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


async def get_average_check():

    transactions = await get_month_transactions()

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


async def get_average_day_expense():

    transactions = await get_month_transactions()

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


async def get_month_operations():

    transactions = await get_month_transactions()

    return len(transactions)


async def get_analytics():

    stats = await get_month_statistics()

    users = await get_users_statistics()

    categories = await get_categories_statistics()

    biggest = await get_biggest_purchase()

    average_check = await get_average_check()

    average_day = await get_average_day_expense()

    operations = await get_month_operations()

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