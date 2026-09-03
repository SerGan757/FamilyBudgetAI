-- Controlled Documents v1 migration. Verify the target database before running.
-- This file is intentionally not executed by application startup.

BEGIN;

CREATE TABLE document_categories (
    id SERIAL PRIMARY KEY,
    family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    code VARCHAR(32),
    name VARCHAR(80),
    emoji VARCHAR(16) NOT NULL DEFAULT '📁',
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    CONSTRAINT uq_document_categories_family_name UNIQUE (family_id, name),
    CONSTRAINT uq_document_categories_family_code UNIQUE (family_id, code)
);
CREATE INDEX ix_document_categories_family_id ON document_categories(family_id);
CREATE INDEX ix_document_categories_family_active_sort ON document_categories(family_id, is_active, sort_order);

CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES document_categories(id) ON DELETE RESTRICT,
    title VARCHAR(150) NOT NULL,
    owner_name VARCHAR(100),
    note VARCHAR(1000),
    expires_at TIMESTAMP WITHOUT TIME ZONE,
    access_level VARCHAR(10) NOT NULL DEFAULT 'family',
    created_by_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    CONSTRAINT ck_documents_access_level CHECK (access_level IN ('family', 'private'))
);
CREATE INDEX ix_documents_family_id ON documents(family_id);
CREATE INDEX ix_documents_category_id ON documents(category_id);
CREATE INDEX ix_documents_created_by_user_id ON documents(created_by_user_id);
CREATE INDEX ix_documents_family_title ON documents(family_id, title);
CREATE INDEX ix_documents_category_created ON documents(category_id, created_at);

CREATE TABLE document_files (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    telegram_file_id VARCHAR(255) NOT NULL,
    telegram_file_unique_id VARCHAR(255),
    file_type VARCHAR(20) NOT NULL,
    original_filename VARCHAR(255),
    mime_type VARCHAR(100),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);
CREATE INDEX ix_document_files_document_id ON document_files(document_id);
CREATE INDEX ix_document_files_document_sort ON document_files(document_id, sort_order);

COMMIT;

-- ROLLBACK, only after application rollback and an explicit data-retention decision:
-- BEGIN;
-- DROP TABLE document_files;
-- DROP TABLE documents;
-- DROP TABLE document_categories;
-- COMMIT;
