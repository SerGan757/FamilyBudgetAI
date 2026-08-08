BEGIN;

ALTER TABLE families
    ADD COLUMN IF NOT EXISTS temporary_screen_ttl INTEGER;

UPDATE families
SET temporary_screen_ttl = 20
WHERE temporary_screen_ttl IS NULL;

ALTER TABLE families
    ALTER COLUMN temporary_screen_ttl SET DEFAULT 20;

ALTER TABLE families
    ALTER COLUMN temporary_screen_ttl SET NOT NULL;

COMMIT;
