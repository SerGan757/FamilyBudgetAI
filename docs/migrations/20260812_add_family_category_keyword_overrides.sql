-- Controlled Categories v1 migration. Do not run from application startup.
BEGIN;

CREATE TABLE family_category_keyword_overrides (
    id SERIAL PRIMARY KEY,
    family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    category_key VARCHAR(32) NOT NULL,
    keyword VARCHAR(100) NOT NULL,
    normalized_keyword VARCHAR(100) NOT NULL,
    action VARCHAR(10) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    CONSTRAINT ck_family_category_keyword_action
        CHECK (action IN ('add', 'disable')),
    CONSTRAINT uq_family_category_keyword_override
        UNIQUE (family_id, category_key, normalized_keyword)
);

CREATE INDEX ix_family_category_keyword_overrides_family_id
    ON family_category_keyword_overrides(family_id);
CREATE INDEX ix_family_category_keyword_family_category
    ON family_category_keyword_overrides(family_id, category_key);

COMMIT;

-- Rollback only after application rollback and an explicit data-retention decision:
-- DROP TABLE family_category_keyword_overrides;
