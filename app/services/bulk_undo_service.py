"""Stateless, authenticated batch Undo using existing transaction columns.

The callback contains bounds and a MAC of the exact saved ID set, author,
family and shared creation time. Bounds/timestamps are only lookup hints.
No FSM, process cache, schema change or new signing secret is required.
"""
import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database.db import SessionLocal
from app.database.models import Transaction
from app.services.family_activity_service import touch_family_activity
from app.services.undo_service import UNDO_TTL, UndoResult


def batch_signature(transactions, signing_key: str) -> str:
    """Authenticate membership, not just bounds; never assume contiguous IDs."""
    if not signing_key:
        raise ValueError("Batch Undo requires a signing key")
    rows = sorted(transactions, key=lambda row: row.id)
    payload = "bulk-undo-v1|" + "|".join(
        f"{row.id},{row.family_id},{row.user_id},{row.created_at.isoformat()}"
        for row in rows
    )
    digest = hmac.new(signing_key.encode(), payload.encode(), hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


async def undo_transaction_batch(
    first_id: int, last_id: int, signature: str, family_id: int, user_id: int,
    signing_key: str, *, now: datetime | None = None,
) -> UndoResult:
    def result(status):
        return UndoResult(status, first_id, "batch")

    if not 0 < first_id < last_id <= 2**31 - 1 or len(signature) != 22:
        return result("forbidden")
    async with SessionLocal() as session:
        async with session.begin():
            # Do not lock the anchor separately: all row locks are acquired
            # in ID order, including concurrent/double-click requests.
            anchor = await session.scalar(select(Transaction).where(Transaction.id == first_id))
            if anchor is None:
                return result("already_deleted")
            if anchor.family_id != family_id:
                return result("forbidden")
            if anchor.user_id != user_id:
                return result("not_author")
            rows = list((await session.execute(select(Transaction).where(
                Transaction.id.between(first_id, last_id),
                Transaction.created_at == anchor.created_at,
                Transaction.family_id == family_id,
                Transaction.user_id == user_id,
            ).order_by(Transaction.id).with_for_update()
                .execution_options(populate_existing=True))).scalars())
            if (len(rows) < 2 or rows[0].id != first_id or rows[-1].id != last_id
                or not hmac.compare_digest(
                batch_signature(rows, signing_key).encode(), signature.encode(),
            )):
                # Missing members, altered bounds or an unrelated row with
                # the same timestamp must never result in a partial Undo.
                return result("already_deleted")
            if any(row.is_recurring or row.family_id != family_id or row.user_id != user_id
                   for row in rows):
                return result("forbidden")
            current_time = now or datetime.now(timezone.utc).replace(tzinfo=None)
            if any(row.created_at is None or not timedelta(0) <= current_time - row.created_at <= UNDO_TTL
                   for row in rows):
                return result("expired")
            for row in rows:
                await session.delete(row)
            await session.flush()
            await touch_family_activity(family_id, session=session)
        return result("deleted")
