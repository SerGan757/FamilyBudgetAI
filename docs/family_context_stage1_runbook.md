# Family context: stage 1 deployment

## Warning

`app/database/init_db.py` currently contains legacy startup DDL/DML. This stage
does not add `telegram_chat_id` there. Production schema changes must be made
only by the reviewed migration SQL, never by application startup code.

## Controlled local verification

1. Restore a production-like backup into a local PostgreSQL database.
2. Record row counts for `families`, `users`, `transactions`, and
   `recurring_payments`.
3. Execute the **UP** section of `migrations/20260731_add_families_telegram_chat_id.sql` once.
4. Verify `telegram_chat_id` is nullable and the partial unique index exists.
5. With exactly one legacy family whose `telegram_chat_id` is NULL, send `/start`
   from the intended chat and confirm only that family receives the chat ID.
6. Send `/start` again from the same chat: no second family is created.
7. Create a new chat: it receives a new family and a unique invite code.
8. Compare the row counts from step 2; no existing records may be removed.

Do not run this SQL on Railway until a backup and a reviewed deployment window
are available.
