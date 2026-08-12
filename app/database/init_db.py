import asyncio

from sqlalchemy import text

from app.database.db import Base, engine
from app.database.models import (
    Transaction,
    RecurringPayment,
    FamilyCategoryKeywordOverride,
)


async def init_db():

    async with engine.begin() as conn:
     
        # Пока проект в разработке —
        # пересоздаем таблицу автоматически.
        # Savings Goal v1 is deployed only through its controlled migration;
        # startup must not create those production tables implicitly.
        controlled_tables = {
            "savings_goals", "goal_contributions",
            "family_category_keyword_overrides",
        }
        existing_tables = [
            table for table in Base.metadata.sorted_tables
            if table.name not in controlled_tables
        ]
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(sync_conn, tables=existing_tables)
        )

        # Backward-compatible Family metadata migration. Existing rows and
        # related user/transaction/payment data are preserved.
        for statement in (
            "ALTER TABLE families ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE families ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE families ADD COLUMN IF NOT EXISTS country VARCHAR(100)",
            "ALTER TABLE families ADD COLUMN IF NOT EXISTS city VARCHAR(100)",
            "ALTER TABLE families ADD COLUMN IF NOT EXISTS language VARCHAR(10) DEFAULT 'ru'",
            "ALTER TABLE families ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) DEFAULT 'Europe/Berlin'",
            "ALTER TABLE families ADD COLUMN IF NOT EXISTS currency VARCHAR(3) DEFAULT 'EUR'",
            "ALTER TABLE families ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
            "ALTER TABLE families ADD COLUMN IF NOT EXISTS plan VARCHAR(20) DEFAULT 'free'",
            "ALTER TABLE families ADD COLUMN IF NOT EXISTS paid_until TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE families ADD COLUMN IF NOT EXISTS trial_until TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE families ADD COLUMN IF NOT EXISTS last_payment_at TIMESTAMP WITHOUT TIME ZONE",
            "ALTER TABLE families ADD COLUMN IF NOT EXISTS disabled_reason VARCHAR(255)",
        ):
            await conn.execute(text(statement))

        await conn.execute(text(
            "UPDATE families SET "
            "created_at = COALESCE(created_at, CURRENT_TIMESTAMP AT TIME ZONE 'UTC'), "
            "language = COALESCE(language, 'ru'), "
            "timezone = COALESCE(timezone, 'Europe/Berlin'), "
            "currency = COALESCE(currency, 'EUR'), "
            "is_active = COALESCE(is_active, TRUE), "
            "plan = COALESCE(plan, 'free') "
            "WHERE created_at IS NULL OR language IS NULL OR timezone IS NULL "
            "OR currency IS NULL OR is_active IS NULL OR plan IS NULL"
        ))
        for statement in (
            "ALTER TABLE families ALTER COLUMN created_at SET DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')",
            "ALTER TABLE families ALTER COLUMN created_at SET NOT NULL",
            "ALTER TABLE families ALTER COLUMN language SET DEFAULT 'ru'",
            "ALTER TABLE families ALTER COLUMN language SET NOT NULL",
            "ALTER TABLE families ALTER COLUMN timezone SET DEFAULT 'Europe/Berlin'",
            "ALTER TABLE families ALTER COLUMN timezone SET NOT NULL",
            "ALTER TABLE families ALTER COLUMN currency SET DEFAULT 'EUR'",
            "ALTER TABLE families ALTER COLUMN currency SET NOT NULL",
            "ALTER TABLE families ALTER COLUMN is_active SET DEFAULT TRUE",
            "ALTER TABLE families ALTER COLUMN is_active SET NOT NULL",
            "ALTER TABLE families ALTER COLUMN plan SET DEFAULT 'free'",
            "ALTER TABLE families ALTER COLUMN plan SET NOT NULL",
        ):
            await conn.execute(text(statement))

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
