from datetime import date

from sqlalchemy import delete, select, update

from app.database.db import SessionLocal
from app.database.models import (
    RecurringPayment,
    Transaction,
)


async def add_payment(
    family_id: int,
    title: str,
    amount: float,
    transaction_type: str,
    category: str,
    frequency: str = "monthly",
    interval_value: int = 1,
    day_of_month: int = 1,
    month_of_year: int = 1,
    payer: str = "Общий",
):

    async with SessionLocal() as session:

        payment = RecurringPayment(
            family_id=family_id,
            title=title,
            amount=amount,
            type=transaction_type,
            category=category,
            frequency=frequency,
            interval_value=interval_value,
            day_of_month=day_of_month,
            month_of_year=month_of_year,
            payer=payer,
        )

        session.add(payment)

        await session.commit()
        await session.refresh(payment)

        return payment


async def get_payments(
    family_id: int,
    active_only: bool = False,
):

    async with SessionLocal() as session:

        query = (
            select(RecurringPayment)
            .where(
                RecurringPayment.family_id == family_id
            )
        )

        if active_only:
            query = query.where(
                RecurringPayment.active.is_(True)
            )

        result = await session.execute(
            query.order_by(
                RecurringPayment.day_of_month,
                RecurringPayment.title,
            )
        )

        return result.scalars().all()


async def get_payment(
    payment_id: int,
    family_id: int,
):

    async with SessionLocal() as session:

        result = await session.execute(
            select(RecurringPayment).where(
                RecurringPayment.id == payment_id,
                RecurringPayment.family_id == family_id,
            )
        )

        return result.scalar_one_or_none()


async def delete_payment(
    payment_id: int,
    family_id: int,
):

    current_period = date.today().replace(day=1)

    async with SessionLocal() as session:

        result = await session.execute(
            select(RecurringPayment).where(
                RecurringPayment.id == payment_id,
                RecurringPayment.family_id == family_id,
            )
        )

        payment = result.scalar_one_or_none()

        if payment is None:
            return False
        await session.execute(
            delete(Transaction).where(
                Transaction.recurring_payment_id == payment.id,
                Transaction.recurring_period == current_period,
            )
        )

        await session.delete(payment)

        await session.commit()

        return True


async def update_payment(
    payment_id: int,
    family_id: int,
    title: str,
    amount: float,
    transaction_type: str,
    category: str,
):

    current_period = date.today().replace(day=1)

    async with SessionLocal() as session:

        result = await session.execute(
            select(RecurringPayment).where(
                RecurringPayment.id == payment_id,
                RecurringPayment.family_id == family_id,
            )
        )

        payment = result.scalar_one_or_none()

        if payment is None:
            return None

        payment.title = title
        payment.amount = amount
        payment.type = transaction_type
        payment.category = category

        await session.execute(
            update(Transaction)
            .where(
                Transaction.recurring_payment_id == payment.id,
                Transaction.recurring_period == current_period,
            )
            .values(
                title=title,
                amount=amount,
                type=transaction_type,
                category=category,
            )
        )

        await session.commit()

        await session.refresh(payment)

        return payment


async def get_generated_payment_ids(
    family_id: int,
    period: date,
) -> set[int]:
    async with SessionLocal() as session:

        result = await session.execute(
            select(Transaction.recurring_payment_id)
            .join(RecurringPayment)
            .where(
                RecurringPayment.family_id == family_id,
                Transaction.is_recurring.is_(True),
                Transaction.recurring_period == period,
            )
        )

        return {
            payment_id
            for payment_id in result.scalars()
            if payment_id is not None
        }