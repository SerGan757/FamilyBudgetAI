import asyncio

from sqlalchemy import text

from app.database.db import Base, engine
from app.database.models import (
    Transaction,
    RecurringPayment,
)


async def init_db():

    async with engine.begin() as conn:

        # Пока проект в разработке —
        # пересоздаем таблицу автоматически.
        await conn.run_sync(Base.metadata.create_all)

        await conn.execute(
            text(
                "ALTER TABLE recurring_payments "
                "ADD COLUMN IF NOT EXISTS family_id INTEGER"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE transactions "
                "ADD COLUMN IF NOT EXISTS recurring_period DATE"
            )
        )
        await conn.execute(
            text(
                "UPDATE recurring_payments "
                "SET family_id = (SELECT id FROM families ORDER BY id LIMIT 1) "
                "WHERE family_id IS NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE recurring_payments "
                "ALTER COLUMN family_id SET NOT NULL"
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'fk_recurring_payments_family_id'
                    ) THEN
                        ALTER TABLE recurring_payments
                        ADD CONSTRAINT fk_recurring_payments_family_id
                        FOREIGN KEY (family_id) REFERENCES families(id);
                    END IF;
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                DECLARE
                    constraint_name TEXT;
                BEGIN
                    SELECT conname INTO constraint_name
                    FROM pg_constraint
                    WHERE conrelid = 'transactions'::regclass
                      AND contype = 'f'
                      AND confrelid = 'recurring_payments'::regclass;

                    IF constraint_name IS NOT NULL THEN
                        EXECUTE format(
                            'ALTER TABLE transactions DROP CONSTRAINT %I',
                            constraint_name
                        );
                    END IF;

                    ALTER TABLE transactions
                    ADD CONSTRAINT fk_transactions_recurring_payment_id
                    FOREIGN KEY (recurring_payment_id)
                    REFERENCES recurring_payments(id)
                    ON DELETE SET NULL;
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'uq_transactions_recurring_payment_period'
                    ) THEN
                        ALTER TABLE transactions
                        ADD CONSTRAINT uq_transactions_recurring_payment_period
                        UNIQUE (recurring_payment_id, recurring_period);
                    END IF;
                END $$;
                """
            )
        )

    print("Database initialized")


if __name__ == "__main__":
    asyncio.run(init_db())
