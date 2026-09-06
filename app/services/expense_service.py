from datetime import date
from dataclasses import dataclass

from sqlalchemy import select

from app.database.db import SessionLocal
from app.database.models import FamilyCategory, Project, Transaction
from app.services.parser import parse_message
from app.services.category_service import detect_category, detect_category_reference_for_family
from app.services.user_service import get_user_by_telegram_id
from app.services.family_activity_service import touch_family_activity
from app.services.project_service import (
    extract_project_tag, find_family_project_by_tag, suggest_active_family_project,
)


@dataclass
class PendingProjectTransaction:
    status: str
    tag: str
    parsed: dict
    project: Project | None = None
    suggestion: Project | None = None


async def save_transaction(
    text: str,
    telegram_id: int,
    family_id: int,
):

    try:
        transaction_text, project_tag = extract_project_tag(text)
    except ValueError:
        return "INVALID_PROJECT_TAG"

    parsed = parse_message(transaction_text)

    if parsed is None:
        return "PARSE_ERROR"

    user = await get_user_by_telegram_id(telegram_id)

    if user is None:
        return "USER_NOT_FOUND"
    if user.family_id != family_id:
        return "USER_FAMILY_MISMATCH"

    if parsed["type"] in {"income", "expense"}:
        icon, category, custom_category_id = await detect_category_reference_for_family(
            family_id, parsed["title"], parsed["type"],
        )
        parsed["category"] = f"{icon} {category}"
        parsed["custom_category_id"] = custom_category_id

    project = None
    if project_tag is not None:
        project = await find_family_project_by_tag(family_id, project_tag)
        if project is None:
            suggestion = await suggest_active_family_project(family_id, project_tag)
            return PendingProjectTransaction(
                status="not_found", tag=project_tag, parsed=parsed, suggestion=suggestion,
            )
        if not project.is_active:
            return PendingProjectTransaction(
                status="inactive", tag=project_tag, parsed=parsed, project=project,
            )

    transaction = await create_transaction(
        user_id=user.id,
        family_id=family_id,
        title=parsed["title"],
        amount=parsed["amount"],
        transaction_type=parsed["type"],
        category=parsed["category"],
        project_id=project.id if project is not None else None,
        custom_category_id=parsed.get("custom_category_id"),
    )

    if project is not None:
        transaction.project_name = project.name

    return transaction


async def create_transaction(
    user_id: int,
    family_id: int,
    title: str,
    amount: float,
    transaction_type: str = "expense",
    category: str = "📦 Прочее",
    is_recurring: bool = False,
    recurring_payment_id: int | None = None,
    recurring_period: date | None = None,
    project_id: int | None = None,
    custom_category_id: int | None = None,
):

    if transaction_type not in {"income", "expense"}:
        raise ValueError("Unsupported transaction type")
    income_icon, income_category = detect_category(title, "income")
    if transaction_type == "income":
        category = f"{income_icon} {income_category}"
        custom_category_id = None
    elif custom_category_id is None and category == f"{income_icon} {income_category}":
        expense_icon, expense_category = detect_category(title, "expense")
        category = f"{expense_icon} {expense_category}"

    async with SessionLocal() as session:

        if project_id is not None:
            project_result = await session.execute(
                select(Project).where(
                    Project.id == project_id,
                    Project.family_id == family_id,
                )
            )
            if project_result.scalar_one_or_none() is None:
                raise ValueError("Project does not belong to transaction family")

        if custom_category_id is not None:
            category_result = await session.execute(
                select(FamilyCategory).where(
                    FamilyCategory.id == custom_category_id,
                    FamilyCategory.family_id == family_id,
                    FamilyCategory.is_active.is_(True),
                )
            )
            if category_result.scalar_one_or_none() is None:
                raise ValueError("Custom category does not belong to transaction family")

        transaction = Transaction(
            user_id=user_id,
            family_id=family_id,
            title=title,
            amount=amount,
            type=transaction_type,
            category=category,
            is_recurring=is_recurring,
            recurring_payment_id=recurring_payment_id,
            recurring_period=recurring_period,
            project_id=project_id,
            custom_category_id=custom_category_id,
        )

        session.add(transaction)

        if not is_recurring:
            await touch_family_activity(family_id, session=session)

        await session.commit()

        await session.refresh(transaction)

        return transaction


async def update_recurring_transaction(
    transaction: Transaction,
    title: str,
    amount: float,
    transaction_type: str,
    category: str,
):

    async with SessionLocal() as session:

        db_transaction = await session.get(
            Transaction,
            transaction.id,
        )

        if db_transaction is None:
            return None

        db_transaction.title = title
        db_transaction.amount = amount
        db_transaction.type = transaction_type
        db_transaction.category = category

        if db_transaction.family_id is not None:
            await touch_family_activity(db_transaction.family_id, session=session)

        await session.commit()
        await session.refresh(db_transaction)

        return db_transaction        


async def get_transaction(transaction_id: int, family_id: int):

    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction).where(
                Transaction.id == transaction_id,
                Transaction.family_id == family_id,
            )
        )

        return result.scalar_one_or_none()
