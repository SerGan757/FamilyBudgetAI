-- Manual migration for a controlled deployment. Do not execute at application startup.
-- Preconditions: verified PostgreSQL backup and a maintenance window.

-- UP
BEGIN;
ALTER TABLE families ADD COLUMN telegram_chat_id BIGINT;
CREATE UNIQUE INDEX uq_families_telegram_chat_id
    ON families (telegram_chat_id)
    WHERE telegram_chat_id IS NOT NULL;
COMMIT;

-- DOWN (only after confirming no application code uses the column)
-- BEGIN;
-- DROP INDEX IF EXISTS uq_families_telegram_chat_id;
-- ALTER TABLE families DROP COLUMN telegram_chat_id;
-- COMMIT;
