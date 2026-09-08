-- Controlled Documents hardening migration (Stage 2 schema).
-- Diagnose existing data and stop on conflicts; never repair or delete data automatically.
-- This file is intentionally not executed by application startup.

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM document_files
        GROUP BY document_id, sort_order
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Documents Stage 2 blocked: duplicate document_files (document_id, sort_order) found';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM document_files
        WHERE telegram_file_unique_id IS NOT NULL
        GROUP BY document_id, telegram_file_unique_id
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Documents Stage 2 blocked: duplicate document_files (document_id, telegram_file_unique_id) found';
    END IF;
END
$$;

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS upload_session_key VARCHAR(36);

CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_upload_session_key
    ON documents(upload_session_key)
    WHERE upload_session_key IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_document_files_document_sort'
          AND conrelid = 'document_files'::regclass
    ) THEN
        ALTER TABLE document_files
            ADD CONSTRAINT uq_document_files_document_sort
            UNIQUE (document_id, sort_order);
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_document_files_document_file_unique
    ON document_files(document_id, telegram_file_unique_id)
    WHERE telegram_file_unique_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS temporary_telegram_messages (
    id BIGSERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    delete_after TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    locked_until TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    last_attempt_at TIMESTAMP WITHOUT TIME ZONE,
    CONSTRAINT uq_temporary_telegram_messages_chat_message
        UNIQUE (chat_id, message_id),
    CONSTRAINT ck_temporary_telegram_messages_status
        CHECK (status IN ('pending', 'processing', 'failed')),
    CONSTRAINT ck_temporary_telegram_messages_attempts
        CHECK (attempts >= 0)
);

CREATE INDEX IF NOT EXISTS ix_temporary_telegram_messages_status_delete_after
    ON temporary_telegram_messages(status, delete_after);

CREATE INDEX IF NOT EXISTS ix_temporary_telegram_messages_locked_until
    ON temporary_telegram_messages(locked_until);

COMMIT;

-- Rollback must be executed only after application rollback and an explicit
-- decision about pending Telegram-message deletion jobs.
-- BEGIN;
-- DROP TABLE IF EXISTS temporary_telegram_messages;
-- DROP INDEX IF EXISTS uq_document_files_document_file_unique;
-- ALTER TABLE document_files DROP CONSTRAINT IF EXISTS uq_document_files_document_sort;
-- DROP INDEX IF EXISTS uq_documents_upload_session_key;
-- ALTER TABLE documents DROP COLUMN IF EXISTS upload_session_key;
-- COMMIT;
