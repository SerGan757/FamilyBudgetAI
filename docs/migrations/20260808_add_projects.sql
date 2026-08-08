-- Controlled Projects v1 migration. Run only against a verified target database.
-- Existing families, users, transactions and recurring_payments are not modified.

-- UP
BEGIN;

CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    family_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    tag VARCHAR(30) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    CONSTRAINT fk_projects_family_id
        FOREIGN KEY (family_id) REFERENCES families(id) ON DELETE CASCADE,
    CONSTRAINT uq_projects_family_tag UNIQUE (family_id, tag)
);

CREATE INDEX ix_projects_family_id ON projects(family_id);
CREATE INDEX ix_projects_family_active ON projects(family_id, is_active);

ALTER TABLE transactions ADD COLUMN project_id INTEGER NULL;
ALTER TABLE transactions
    ADD CONSTRAINT fk_transactions_project_id
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL;
CREATE INDEX ix_transactions_project_id ON transactions(project_id);

COMMIT;

-- ROLLBACK (only before Projects v1 data is used and after application rollback)
-- BEGIN;
-- DROP INDEX IF EXISTS ix_transactions_project_id;
-- ALTER TABLE transactions DROP CONSTRAINT IF EXISTS fk_transactions_project_id;
-- ALTER TABLE transactions DROP COLUMN IF EXISTS project_id;
-- DROP TABLE IF EXISTS projects;
-- COMMIT;
