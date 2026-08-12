import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.categories import CATEGORIES
from app.database.db import SessionLocal
from app.database.models import FamilyCategoryKeywordOverride


EDITABLE_CATEGORY_KEYS = tuple(
    key for key in CATEGORIES if key not in {"income", "other"}
)
SETTINGS_CATEGORY_KEYS = (*EDITABLE_CATEGORY_KEYS, "other")


@dataclass(frozen=True)
class EffectiveKeyword:
    keyword: str
    normalized_keyword: str
    source: str  # system | family


@dataclass(frozen=True)
class KeywordMutationResult:
    status: str
    conflict_category_key: str | None = None


@dataclass(frozen=True)
class BulkKeywordItemResult:
    keyword: str
    status: str
    conflict_category_key: str | None = None


@dataclass(frozen=True)
class BulkKeywordResult:
    items: tuple[BulkKeywordItemResult, ...] = ()
    limit_exceeded: bool = False

    def count(self, status: str) -> int:
        return sum(item.status == status for item in self.items)


def normalize_keyword(keyword: str) -> str:
    return re.sub(r"\s+", " ", (keyword or "").strip().lower())


def parse_keyword_list(text: str) -> list[str]:
    """Split only on commas, normalize, remove blanks and stable-deduplicate."""
    unique: dict[str, None] = {}
    for part in (text or "").split(","):
        normalized = normalize_keyword(part)
        if normalized:
            unique.setdefault(normalized, None)
    return list(unique)


def stored_category_for_key(category_key: str) -> str | None:
    category = CATEGORIES.get(category_key)
    if category is None:
        return None
    return f"{category['icon']} {category['title']}"


def category_key_from_stored(stored_category: str) -> str | None:
    return next(
        (
            key for key in CATEGORIES
            if stored_category_for_key(key) == stored_category
        ),
        None,
    )


async def _load_overrides(
    family_id: int, session: AsyncSession,
) -> list[FamilyCategoryKeywordOverride]:
    result = await session.execute(
        select(FamilyCategoryKeywordOverride).where(
            FamilyCategoryKeywordOverride.family_id == family_id,
        ).order_by(FamilyCategoryKeywordOverride.id)
    )
    return list(result.scalars().all())


def _build_catalog(
    overrides: list[FamilyCategoryKeywordOverride],
) -> dict[str, list[EffectiveKeyword]]:
    by_key = {(row.category_key, row.normalized_keyword): row for row in overrides}
    catalog: dict[str, list[EffectiveKeyword]] = {}
    for category_key, category in CATEGORIES.items():
        active: dict[str, EffectiveKeyword] = {}
        for keyword in category["keywords"]:
            normalized = normalize_keyword(keyword)
            row = by_key.get((category_key, normalized))
            if row is None or row.action != "disable":
                active[normalized] = EffectiveKeyword(keyword, normalized, "system")
        for row in overrides:
            if row.category_key == category_key and row.action == "add":
                active[row.normalized_keyword] = EffectiveKeyword(
                    row.keyword, row.normalized_keyword, "family",
                )
        catalog[category_key] = list(active.values())
    return catalog


async def get_effective_category_catalog(
    family_id: int, *, session: AsyncSession | None = None,
) -> dict[str, list[EffectiveKeyword]]:
    if session is not None:
        return _build_catalog(await _load_overrides(family_id, session))
    async with SessionLocal() as owned_session:
        try:
            overrides = await _load_overrides(family_id, owned_session)
        except ProgrammingError:
            # Safe rollout fallback: ordinary quick input keeps the system
            # catalog until the controlled migration has been applied.
            await owned_session.rollback()
            overrides = []
        return _build_catalog(overrides)


async def get_effective_keywords(
    family_id: int, category_key: str, *, session: AsyncSession | None = None,
) -> list[EffectiveKeyword]:
    catalog = await get_effective_category_catalog(family_id, session=session)
    return catalog.get(category_key, [])


async def get_disabled_keywords(
    family_id: int, category_key: str,
) -> list[FamilyCategoryKeywordOverride]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(FamilyCategoryKeywordOverride).where(
                FamilyCategoryKeywordOverride.family_id == family_id,
                FamilyCategoryKeywordOverride.category_key == category_key,
                FamilyCategoryKeywordOverride.action == "disable",
            ).order_by(FamilyCategoryKeywordOverride.normalized_keyword)
        )
        return list(result.scalars().all())


async def add_family_keyword(
    family_id: int, category_key: str, keyword: str,
) -> KeywordMutationResult:
    normalized = normalize_keyword(keyword)
    if not normalized or len(normalized) > 100 or category_key not in EDITABLE_CATEGORY_KEYS:
        return KeywordMutationResult("invalid")
    async with SessionLocal() as session:
        overrides = await _load_overrides(family_id, session)
        catalog = _build_catalog(overrides)
        for other_key, entries in catalog.items():
            if other_key != category_key and any(
                entry.normalized_keyword == normalized for entry in entries
            ):
                return KeywordMutationResult("conflict", other_key)
        existing = next(
            (
                row for row in overrides
                if row.category_key == category_key
                and row.normalized_keyword == normalized
            ),
            None,
        )
        if existing is not None:
            if existing.action == "disable":
                await session.delete(existing)
                await session.commit()
                return KeywordMutationResult("restored")
            return KeywordMutationResult("duplicate")
        if any(entry.normalized_keyword == normalized for entry in catalog[category_key]):
            return KeywordMutationResult("duplicate")
        session.add(FamilyCategoryKeywordOverride(
            family_id=family_id,
            category_key=category_key,
            keyword=keyword.strip(),
            normalized_keyword=normalized,
            action="add",
        ))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return KeywordMutationResult("duplicate")
        return KeywordMutationResult("added")


async def add_family_keywords(
    family_id: int, category_key: str, text: str, *, limit: int = 30,
) -> BulkKeywordResult:
    keywords = parse_keyword_list(text)
    if len(keywords) > limit:
        return BulkKeywordResult(limit_exceeded=True)
    items = []
    for keyword in keywords:
        result = await add_family_keyword(family_id, category_key, keyword)
        items.append(BulkKeywordItemResult(
            keyword=keyword,
            status="already_exists" if result.status == "duplicate" else result.status,
            conflict_category_key=result.conflict_category_key,
        ))
    return BulkKeywordResult(tuple(items))


async def disable_family_keyword(
    family_id: int, category_key: str, normalized_keyword: str,
) -> KeywordMutationResult:
    normalized = normalize_keyword(normalized_keyword)
    if category_key not in EDITABLE_CATEGORY_KEYS or not normalized:
        return KeywordMutationResult("invalid")
    async with SessionLocal() as session:
        overrides = await _load_overrides(family_id, session)
        existing = next((
            row for row in overrides
            if row.category_key == category_key
            and row.normalized_keyword == normalized
        ), None)
        if existing is not None and existing.action == "add":
            await session.delete(existing)
            await session.commit()
            return KeywordMutationResult("removed")
        system_keyword = next((
            keyword for keyword in CATEGORIES[category_key]["keywords"]
            if normalize_keyword(keyword) == normalized
        ), None)
        if system_keyword is None or (existing is not None and existing.action == "disable"):
            return KeywordMutationResult("not_found")
        session.add(FamilyCategoryKeywordOverride(
            family_id=family_id,
            category_key=category_key,
            keyword=system_keyword,
            normalized_keyword=normalized,
            action="disable",
        ))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return KeywordMutationResult("not_found")
        return KeywordMutationResult("disabled")


async def restore_family_keyword(
    family_id: int, category_key: str, normalized_keyword: str,
) -> bool:
    normalized = normalize_keyword(normalized_keyword)
    async with SessionLocal() as session:
        row = await session.scalar(select(FamilyCategoryKeywordOverride).where(
            FamilyCategoryKeywordOverride.family_id == family_id,
            FamilyCategoryKeywordOverride.category_key == category_key,
            FamilyCategoryKeywordOverride.normalized_keyword == normalized,
            FamilyCategoryKeywordOverride.action == "disable",
        ))
        if row is None:
            return False
        await session.delete(row)
        await session.commit()
        return True
