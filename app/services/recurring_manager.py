from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.db import SessionLocal
from app.database.models import Transaction
from app.services.parser import parse_message
from app.services.recurring_service import (
    add_payment,
    delete_payment,
    get_payments,
    update_payment as update_payment_in_db,
)


def _month_period(target_date: date | None = None) -> date:
    return (target_date or date.today()).replace(day=1)


async def create_payment(family_id: int, text: str):
    """Create a recurring template in the explicitly supplied family."""
    parsed = parse_message(text)
    if parsed is None:
        return None

    return await add_payment(
        family_id=family_id,
        title=parsed["title"],
        amount=parsed["amount"],
        transaction_type=parsed["type"],
        category=parsed["category"],
    )


async def list_payments(family_id: int):
    return await get_payments(family_id, active_only=True)


async def remove_payment(family_id: int, payment_id: int):
    return await delete_payment(payment_id, family_id)


async def update_payment(family_id: int, payment_id: int, text: str):
    parsed = parse_message(text)
    if parsed is None:
        return None

    return await update_payment_in_db(
        payment_id=payment_id,
        family_id=family_id,
        title=parsed["title"],
        amount=parsed["amount"],
        transaction_type=parsed["type"],
        category=parsed["category"],
    )


async def create_month_transactions(
    family_id: int,
    user_id: int,
    target_date: date | None = None,
):
    """Materialize this family's active templates for one calendar month.

    The exact (family, template, period) lookup makes repeated generation
    idempotent even when similarly numbered templates exist in another family.
    """
    period = _month_period(target_date)
    payments = await get_payments(family_id, active_only=True)
    created = updated = unchanged = 0
    details: list[dict[str, object]] = []

    async with SessionLocal() as session:
        try:
            for payment in payments:
                result = await session.execute(
                    select(Transaction).where(
                        Transaction.family_id == family_id,
                        Transaction.recurring_payment_id == payment.id,
                        Transaction.recurring_period == period,
                    )
                )
                transaction = result.scalar_one_or_none()

                if transaction is not None:
                    changed = (
                        transaction.title != payment.title
                        or transaction.amount != payment.amount
                        or transaction.type != payment.type
                        or transaction.category != payment.category
                    )
                    if changed:
                        transaction.title = payment.title
                        transaction.amount = payment.amount
                        transaction.type = payment.type
                        transaction.category = payment.category
                        updated += 1
                        status = "updated"
                    else:
                        unchanged += 1
                        status = "unchanged"

                    details.append(
                        {
                            "title": payment.title,
                            "amount": payment.amount,
                            "type": payment.type,
                            "status": status,
                        }
                    )
                    continue

                session.add(Transaction(
                    user_id=user_id,
                    family_id=family_id,
                    title=payment.title,
                    amount=payment.amount,
                    type=payment.type,
                    category=payment.category,
                    is_recurring=True,
                    recurring_payment_id=payment.id,
                    recurring_period=period,
                ))
                created += 1
                details.append(
                    {
                        "title": payment.title,
                        "amount": payment.amount,
                        "type": payment.type,
                        "status": "created",
                    }
                )
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return {
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "details": details,
    }


async def get_month_recurring_transactions(
    family_id: int,
    target_date: date | None = None,
):
    period = _month_period(target_date)
    async with SessionLocal() as session:
        result = await session.execute(
            select(Transaction)
            .options(selectinload(Transaction.user))
            .where(
                Transaction.family_id == family_id,
                Transaction.is_recurring.is_(True),
                Transaction.recurring_period == period,
                Transaction.recurring_payment_id.is_not(None),
            )
            .order_by(Transaction.title)
        )
        return result.scalars().all()
