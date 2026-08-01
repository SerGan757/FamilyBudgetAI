-- Controlled stage-2 migration. Do not run from init_db.py or application startup.
-- Take and verify a PostgreSQL backup before running.

-- UP
BEGIN;
ALTER TABLE transactions ADD COLUMN family_id INTEGER;
UPDATE transactions t
SET family_id = u.family_id
FROM users u
WHERE t.user_id = u.id AND t.family_id IS NULL;
-- Abort manually if this returns a non-zero value before continuing:
-- SELECT COUNT(*) FROM transactions WHERE family_id IS NULL;
ALTER TABLE transactions
    ADD CONSTRAINT fk_transactions_family_id
    FOREIGN KEY (family_id) REFERENCES families(id) ON DELETE CASCADE;
CREATE INDEX ix_transactions_family_id ON transactions(family_id);
CREATE INDEX ix_transactions_family_created_at ON transactions(family_id, created_at);
CREATE INDEX ix_transactions_family_recurring_period ON transactions(family_id, recurring_period);
ALTER TABLE transactions ALTER COLUMN family_id SET NOT NULL;
COMMIT;

-- ROLLBACK (only after rolling back application code)
-- BEGIN;
-- DROP INDEX IF EXISTS ix_transactions_family_recurring_period;
-- DROP INDEX IF EXISTS ix_transactions_family_created_at;
-- DROP INDEX IF EXISTS ix_transactions_family_id;
-- ALTER TABLE transactions DROP CONSTRAINT IF EXISTS fk_transactions_family_id;
-- ALTER TABLE transactions DROP COLUMN family_id;
-- COMMIT;
