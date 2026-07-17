from sqlalchemy import delete, select

from app.database.db import SessionLocal
from app.database.models import RecurringPayment


async def add_payment(
    title: str,
    amount: float,
    category: str,
    frequency: str = "monthly",
    interval_value: int = 1,
    day_of_month: int = 1,
    month_of_year: int = 1,
    payer: str = "Общий",
):

    async with SessionLocal() as session:

        payment = RecurringPayment(
            title=title,
            amount=amount,
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


async def get_payments():

    async with SessionLocal() as session:

        result = await session.execute(
            select(RecurringPayment).order_by(
                RecurringPayment.day_of_month,
                RecurringPayment.title,
            )
        )

        return result.scalars().all()


async def get_payment(payment_id: int):

    async with SessionLocal() as session:

        result = await session.execute(
            select(RecurringPayment).where(
                RecurringPayment.id == payment_id
            )
        )

        return result.scalar_one_or_none()


async def delete_payment(payment_id: int):

    async with SessionLocal() as session:

        await session.execute(
            delete(RecurringPayment).where(
                RecurringPayment.id == payment_id
            )
        )

        await session.commit()