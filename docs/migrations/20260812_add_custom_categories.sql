-- Controlled Custom Categories v1 migration. Do not run at startup.
BEGIN;
CREATE TABLE family_categories (
 id SERIAL PRIMARY KEY, family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
 name VARCHAR(50) NOT NULL, normalized_name VARCHAR(50) NOT NULL, icon VARCHAR(16) NOT NULL,
 is_active BOOLEAN NOT NULL DEFAULT TRUE,
 created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
 updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
 CONSTRAINT uq_family_category_name UNIQUE (family_id, normalized_name)
);
CREATE INDEX ix_family_categories_family_id ON family_categories(family_id);
CREATE INDEX ix_family_categories_family_active ON family_categories(family_id, is_active);
CREATE TABLE family_category_keywords (
 id SERIAL PRIMARY KEY,
 family_category_id INTEGER NOT NULL REFERENCES family_categories(id) ON DELETE CASCADE,
 family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
 keyword VARCHAR(100) NOT NULL, normalized_keyword VARCHAR(100) NOT NULL,
 created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
 CONSTRAINT uq_family_category_keyword UNIQUE (family_category_id, normalized_keyword)
);
CREATE INDEX ix_family_category_keywords_category_id ON family_category_keywords(family_category_id);
CREATE INDEX ix_family_category_keywords_family_id ON family_category_keywords(family_id);
ALTER TABLE transactions ADD COLUMN custom_category_id INTEGER NULL;
ALTER TABLE transactions ADD CONSTRAINT fk_transactions_custom_category_id
 FOREIGN KEY (custom_category_id) REFERENCES family_categories(id) ON DELETE SET NULL;
CREATE INDEX ix_transactions_custom_category_id ON transactions(custom_category_id);
COMMIT;
