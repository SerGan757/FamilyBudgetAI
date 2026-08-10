-- Controlled Savings Goal v1 migration. Do not run from application startup.
BEGIN;

CREATE TABLE savings_goals (
    id SERIAL PRIMARY KEY,
    family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    target_amount DOUBLE PRECISION NOT NULL CHECK (target_amount > 0),
    deadline DATE NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    completed_at TIMESTAMP WITHOUT TIME ZONE NULL
);
CREATE INDEX ix_savings_goals_family_id ON savings_goals(family_id);
CREATE UNIQUE INDEX uq_savings_goals_one_active_per_family
    ON savings_goals(family_id) WHERE is_active = TRUE;

CREATE TABLE goal_contributions (
    id INTEGER PRIMARY KEY,
    goal_id INTEGER NOT NULL REFERENCES savings_goals(id) ON DELETE CASCADE,
    family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount DOUBLE PRECISION NOT NULL CHECK (amount > 0),
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);
DO $$
DECLARE
    transaction_id_sequence TEXT;
BEGIN
    transaction_id_sequence := pg_get_serial_sequence('transactions', 'id');
    IF transaction_id_sequence IS NULL THEN
        RAISE EXCEPTION 'transactions.id has no PostgreSQL sequence';
    END IF;
    EXECUTE format(
        'ALTER TABLE goal_contributions ALTER COLUMN id SET DEFAULT nextval(%L::regclass)',
        transaction_id_sequence
    );
END $$;
CREATE INDEX ix_goal_contributions_goal_id ON goal_contributions(goal_id);
CREATE INDEX ix_goal_contributions_family_id ON goal_contributions(family_id);
CREATE INDEX ix_goal_contributions_user_id ON goal_contributions(user_id);
CREATE INDEX ix_goal_contributions_created_at ON goal_contributions(created_at);

COMMIT;

-- ROLLBACK (only after application rollback and an explicit data-retention decision)
-- BEGIN;
-- DROP TABLE goal_contributions;
-- DROP TABLE savings_goals;
-- COMMIT;
