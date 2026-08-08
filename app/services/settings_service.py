from sqlalchemy import func, select

from app.database.db import SessionLocal
from app.database.models import Family, RecurringPayment, Transaction, User
from app.services.family_activity_service import touch_family_activity
from app.services.country_catalog import COUNTRIES, get_country


LANGUAGE_CODES = frozenset({"ru", "uk", "de", "en", "be"})
TIMEZONE_VALUES = frozenset({country.timezone for country in COUNTRIES} | {"UTC"})
CURRENCY_CODES = frozenset({country.currency for country in COUNTRIES} | {"USD"})
SETTING_VALUES = {
    "language": LANGUAGE_CODES,
    "timezone": TIMEZONE_VALUES,
    "currency": CURRENCY_CODES,
}
EDITABLE_SETTINGS = frozenset({*SETTING_VALUES, "city"})


def validate_family_setting(field: str, value: str) -> str:
    if field not in EDITABLE_SETTINGS:
        raise ValueError("Unsupported family setting")
    normalized = value.strip()
    if field == "city":
        if not normalized or len(normalized) > 100 or normalized.startswith("/"):
            raise ValueError("Invalid location")
    elif normalized not in SETTING_VALUES[field]:
        raise ValueError("Unsupported setting value")
    return normalized


async def get_current_family_settings(telegram_id: int):
    """Resolve settings through the current registered user, never callback data."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(Family)
            .join(User, User.family_id == Family.id)
            .where(User.telegram_id == telegram_id)
        )
        family = result.scalar_one_or_none()
        if family is None:
            return None
        return {
            "id": family.id,
            "name": family.name,
            "language": family.language,
            "country": family.country,
            "city": family.city,
            "timezone": family.timezone,
            "currency": family.currency,
        }


async def update_current_family_setting(telegram_id: int, field: str, value: str) -> bool:
    """Update one whitelisted setting for the current user's own family."""
    normalized = validate_family_setting(field, value)
    async with SessionLocal() as session:
        result = await session.execute(
            select(Family)
            .join(User, User.family_id == Family.id)
            .where(User.telegram_id == telegram_id)
        )
        family = result.scalar_one_or_none()
        if family is None:
            return False
        setattr(family, field, normalized)
        await touch_family_activity(family.id, session=session)
        await session.commit()
        return True


async def update_current_family_country(telegram_id: int, country_code: str) -> bool:
    """Atomically apply a country's ISO code, default currency and default timezone."""
    country = get_country(country_code)
    if country is None:
        raise ValueError("Unsupported country")
    async with SessionLocal() as session:
        result = await session.execute(
            select(Family)
            .join(User, User.family_id == Family.id)
            .where(User.telegram_id == telegram_id)
        )
        family = result.scalar_one_or_none()
        if family is None:
            return False
        family.country = country.code
        family.currency = country.currency
        family.timezone = country.timezone
        await touch_family_activity(family.id, session=session)
        await session.commit()
        return True


async def get_family_settings_data(family_id: int):
    """Return aggregates for only the current user's family."""
    async with SessionLocal() as session:
        family = await session.get(Family, family_id)
        if family is None:
            return None

        members = await session.execute(
            select(func.count(User.id)).where(User.family_id == family.id)
        )
        transactions = await session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.family_id == family.id
            )
        )
        recurring = await session.execute(
            select(func.count(RecurringPayment.id)).where(RecurringPayment.family_id == family.id)
        )
        return {
            "id": family.id,
            "name": family.name,
            "created_at": family.created_at,
            "members_count": members.scalar_one(),
            "transactions_count": transactions.scalar_one(),
            "recurring_count": recurring.scalar_one(),
        }


async def get_family_members(family_id: int):
    """Return only users belonging to the current user's family."""
    async with SessionLocal() as session:
        members = await session.execute(
            select(User)
            .where(User.family_id == family_id)
            .order_by(User.name, User.id)
        )
        return members.scalars().all()
