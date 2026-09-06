from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, select

from app.database.db import SessionLocal
from app.database.models import Project, Transaction, User
from sqlalchemy.orm import contains_eager, selectinload
from app.services.category_service import detect_category
from app.services.financial_feed_service import get_display_feed


def _transaction_list_query(family_id: int):
    return (
        select(Transaction)
        .outerjoin(
            Project,
            and_(Project.id == Transaction.project_id, Project.family_id == family_id),
        )
        .options(selectinload(Transaction.user), selectinload(Transaction.custom_category), contains_eager(Transaction.project))
    )


def _expense_category_label(transaction: Transaction) -> str:
    if transaction.custom_category is not None:
        return f"{transaction.custom_category.icon} {transaction.custom_category.name}"
    income_icon, income_name = detect_category(transaction.title, "income")
    if transaction.category == f"{income_icon} {income_name}":
        expense_icon, expense_name = detect_category(transaction.title, "expense")
        return f"{expense_icon} {expense_name}"
    return transaction.category


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
                Transaction.family_id == family_id,
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
    selected_date: date | None = None,
    offset: int = 0,
    limit: int = 20,
):

    today = datetime.combine(
        selected_date or date.today(),
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
    display_operations, display_total, goal_total = await get_display_feed(
        family_id, start=today, end=tomorrow, offset=offset, limit=limit,
    )

    async with SessionLocal() as session:

        count_result = await session.execute(
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.family_id == family_id,
                Transaction.created_at >= today,
                Transaction.created_at < tomorrow,
            )
        )

        total = count_result.scalar() or 0

        recurring_count_result = await session.execute(
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.family_id == family_id,
                Transaction.created_at >= today,
                Transaction.created_at < tomorrow,
                Transaction.is_recurring.is_(True),
            )
        )
        recurring_count = recurring_count_result.scalar() or 0

        result = await session.execute(
            _transaction_list_query(family_id)
            .where(
                Transaction.family_id == family_id,
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
            "transactions": display_operations,
            "total": display_total,
            "goal_contributions": goal_total,
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
    display_operations, display_total, goal_total = await get_display_feed(
        family_id, start=month_start, end=next_month, offset=offset, limit=limit,
    )

    async with SessionLocal() as session:
        count_result = await session.execute(
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.family_id == family_id,
                Transaction.created_at >= month_start,
                Transaction.created_at < next_month,
            )
        )

        total = count_result.scalar() or 0

        recurring_income_count_result = await session.execute(
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.family_id == family_id,
                Transaction.created_at >= month_start,
                Transaction.created_at < next_month,
                Transaction.is_recurring.is_(True),
                Transaction.type == "income",
            )
        )
        recurring_income_count = recurring_income_count_result.scalar() or 0
        recurring_expense_count_result = await session.execute(
            select(func.count()).select_from(Transaction).where(
                Transaction.family_id == family_id,
                Transaction.created_at >= month_start,
                Transaction.created_at < next_month,
                Transaction.is_recurring.is_(True),
                Transaction.type == "expense",
            )
        )
        recurring_expense_count = recurring_expense_count_result.scalar() or 0

        result = await session.execute(
            _transaction_list_query(family_id)
            .where(
                Transaction.family_id == family_id,
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
        "transactions": display_operations,
        "total": display_total,
        "goal_contributions": goal_total,
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
                Transaction.family_id == family_id,
                Transaction.created_at >= month_start,
                Transaction.created_at < next_month,
            )
        )
        data = build_balance_data(result.scalars().all())
    _, _, goal_total = await get_display_feed(
        family_id, start=month_start, end=next_month, limit=0,
    )
    data["goal_contributions"] = goal_total
    data["free_balance"] = data["balance"] - goal_total
    return data


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

async def get_month_transactions(family_id: int, year: int | None = None, month: int | None = None):

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

    async with SessionLocal() as session:

        result = await session.execute(
            _transaction_list_query(family_id)
            .where(
                Transaction.family_id == family_id,
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

        category = _expense_category_label(t)
        categories[category] = (
            categories.get(
                category,
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


async def get_project_expense_statistics(family_id: int, year: int, month: int):
    month_start = datetime(year, month, 1)
    next_month = (
        datetime(year + 1, 1, 1)
        if month == 12
        else datetime(year, month + 1, 1)
    )
    project_total = func.sum(Transaction.amount)
    async with SessionLocal() as session:
        result = await session.execute(
            select(Project.name, project_total)
            .join(Transaction, Transaction.project_id == Project.id)
            .where(
                Transaction.family_id == family_id,
                Project.family_id == family_id,
                Transaction.type == "expense",
                Transaction.project_id.is_not(None),
                Transaction.created_at >= month_start,
                Transaction.created_at < next_month,
            )
            .group_by(Project.id, Project.name)
            .order_by(project_total.desc())
            .limit(5)
        )
        return [(name, float(amount)) for name, amount in result.all()]


async def get_analytics(
    family_id: int, year: int | None = None, month: int | None = None,
    *, include_goal: bool = False,
):
    today = date.today()
    year, month = year or today.year, month or today.month
    stats = await get_month_statistics(family_id, year, month)
    transactions = await get_month_transactions(family_id, year, month)
    projects = await get_project_expense_statistics(family_id, year, month)
    goal = None
    if include_goal:
        from app.services.savings_goal_service import get_goal_snapshot
        try:
            goal = await get_goal_snapshot(family_id, year, month)
        except Exception:
            # Existing analytics stays available during a controlled rollout
            # before the new tables are migrated.
            goal = None
    expenses = [t for t in transactions if t.type == "expense"]
    incomes = [t for t in transactions if t.type == "income"]
    users, categories, by_day_expense, by_day_income = {}, {}, {}, {}
    for t in expenses:
        name = t.user.name if t.user else "Неизвестно"
        users[name] = users.get(name, 0) + t.amount
        category = _expense_category_label(t)
        categories[category] = categories.get(category, 0) + t.amount
        by_day_expense[t.created_at.date()] = by_day_expense.get(t.created_at.date(), 0) + t.amount
    for t in incomes:
        by_day_income[t.created_at.date()] = by_day_income.get(t.created_at.date(), 0) + t.amount
    biggest_expense = max(expenses, key=lambda t: t.amount) if expenses else None
    biggest_income = max(incomes, key=lambda t: t.amount) if incomes else None
    return {**stats, "operations": len(transactions), "income_operations": len(incomes),
            "expense_operations": len(expenses), "ordinary_operations": len([t for t in transactions if not t.is_recurring]),
            "recurring_operations": len([t for t in transactions if t.is_recurring]),
            "average_check": round(sum(t.amount for t in expenses) / len(expenses), 2) if expenses else 0,
            "average_day": round(sum(by_day_expense.values()) / len(by_day_expense), 2) if by_day_expense else 0,
            "users": sorted(users.items(), key=lambda x: x[1], reverse=True),
            "categories": sorted(categories.items(), key=lambda x: x[1], reverse=True),
            "biggest": biggest_expense, "biggest_income": biggest_income,
            "projects": projects, "goal": goal,
            "costliest_day": max(by_day_expense.items(), key=lambda x: x[1]) if by_day_expense else None,
            "best_income_day": max(by_day_income.items(), key=lambda x: x[1]) if by_day_income else None}
