import re
from dataclasses import dataclass
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from app.data.categories import CATEGORIES
from app.database.db import SessionLocal
from app.database.models import FamilyCategory, FamilyCategoryKeyword, Transaction
from app.i18n import category_label
from app.i18n.translations import SUPPORTED_LANGUAGES
from app.services.category_override_service import get_effective_category_catalog, normalize_keyword, parse_keyword_list

MAX_CUSTOM_CATEGORIES = 20
MAX_CUSTOM_KEYWORDS = 100
ICONS = ("🎬","🎮","🎵","🎓","💇","🎁","✈️","🏋️","📚","❤️","⭐","🧾")

def normalize_category_name(value): return re.sub(r"\s+", " ", (value or "").strip().lower())
def custom_label(category): return f"{category.icon} {category.name}"

def _reserved_names():
    names = {normalize_category_name(value["title"]) for value in CATEGORIES.values()}
    for value in CATEGORIES.values():
        stored = f'{value["icon"]} {value["title"]}'
        names.update(
            normalize_category_name(category_label(language, stored).split(maxsplit=1)[-1])
            for language in SUPPORTED_LANGUAGES
        )
    return names

@dataclass(frozen=True)
class CustomResult:
    status: str
    category: object | None = None
    conflict_label: str | None = None

async def list_custom_categories(family_id, active=None):
    async with SessionLocal() as s:
        q=select(FamilyCategory).options(selectinload(FamilyCategory.keywords)).where(FamilyCategory.family_id==family_id)
        if active is not None: q=q.where(FamilyCategory.is_active.is_(active))
        return list((await s.scalars(q.order_by(FamilyCategory.id))).all())

async def get_custom_category(family_id, category_id):
    async with SessionLocal() as s:
        return await s.scalar(select(FamilyCategory).options(selectinload(FamilyCategory.keywords)).where(FamilyCategory.id==category_id, FamilyCategory.family_id==family_id))

async def create_custom_category(family_id, name, icon, keywords=""):
    normalized=normalize_category_name(name)
    if not normalized or len(name.strip())>50 or not icon or len(icon)>16: return CustomResult("invalid")
    if normalized in _reserved_names(): return CustomResult("reserved")
    async with SessionLocal() as s:
        if await s.scalar(select(func.count()).select_from(FamilyCategory).where(FamilyCategory.family_id==family_id)) >= MAX_CUSTOM_CATEGORIES: return CustomResult("limit")
        if await s.scalar(select(FamilyCategory.id).where(FamilyCategory.family_id==family_id, FamilyCategory.normalized_name==normalized)): return CustomResult("duplicate")
        category=FamilyCategory(family_id=family_id,name=name.strip(),normalized_name=normalized,icon=icon,is_active=True)
        s.add(category); await s.flush()
        await s.commit(); await s.refresh(category)
    if keywords: await add_custom_keywords(family_id, category.id, keywords)
    return CustomResult("created", category)

async def _keyword_conflict(family_id, category_id, keyword):
    catalog=await get_effective_category_catalog(family_id)
    for key, entries in catalog.items():
        if any(e.normalized_keyword==keyword for e in entries): return f"system:{key}"
    cats=await list_custom_categories(family_id, True)
    for cat in cats:
        if cat.id != category_id and any(k.normalized_keyword==keyword for k in cat.keywords): return f"custom:{cat.id}"
    return None

async def add_custom_keywords(family_id, category_id, text):
    words=parse_keyword_list(text)
    if len(words)>30: return {"limit_exceeded":True,"items":[]}
    cat=await get_custom_category(family_id,category_id)
    if not cat or not cat.is_active: return {"not_found":True,"items":[]}
    active={k.normalized_keyword for k in cat.keywords}
    if len(active | set(words))>MAX_CUSTOM_KEYWORDS: return {"category_limit":True,"items":[]}
    items=[]
    for word in words:
        if word in active: items.append((word,"already_exists",None)); continue
        conflict=await _keyword_conflict(family_id,category_id,word)
        if conflict: items.append((word,"conflict",conflict)); continue
        async with SessionLocal() as s:
            s.add(FamilyCategoryKeyword(family_category_id=category_id,family_id=family_id,keyword=word,normalized_keyword=word))
            try: await s.commit(); active.add(word); items.append((word,"added",None))
            except IntegrityError: await s.rollback(); items.append((word,"already_exists",None))
    return {"items":items}

async def remove_custom_keyword(family_id, category_id, normalized):
    async with SessionLocal() as s:
        result=await s.execute(delete(FamilyCategoryKeyword).where(FamilyCategoryKeyword.family_id==family_id,FamilyCategoryKeyword.family_category_id==category_id,FamilyCategoryKeyword.normalized_keyword==normalize_keyword(normalized)))
        await s.commit(); return bool(result.rowcount)

async def update_custom_category(family_id, category_id, *, name=None, icon=None):
    async with SessionLocal() as s:
        cat=await s.scalar(select(FamilyCategory).where(FamilyCategory.id==category_id,FamilyCategory.family_id==family_id))
        if not cat:return CustomResult("not_found")
        if name is not None:
            normalized=normalize_category_name(name)
            if not normalized or len(name.strip())>50:return CustomResult("invalid")
            if normalized in _reserved_names():return CustomResult("reserved")
            duplicate=await s.scalar(select(FamilyCategory.id).where(FamilyCategory.family_id==family_id,FamilyCategory.normalized_name==normalized,FamilyCategory.id!=category_id))
            if duplicate:return CustomResult("duplicate")
            cat.name=name.strip();cat.normalized_name=normalized
        if icon is not None:
            if not icon or len(icon)>16:return CustomResult("invalid")
            cat.icon=icon
        await s.commit();await s.refresh(cat);return CustomResult("updated",cat)

async def set_custom_category_active(family_id, category_id, active):
    async with SessionLocal() as s:
        cat=await s.scalar(select(FamilyCategory).where(FamilyCategory.id==category_id,FamilyCategory.family_id==family_id))
        if not cat:return False
        cat.is_active=active;await s.commit();return True

async def delete_custom_category(family_id, category_id):
    async with SessionLocal() as s:
        cat=await s.scalar(select(FamilyCategory).where(FamilyCategory.id==category_id,FamilyCategory.family_id==family_id))
        if not cat:return "not_found"
        if await s.scalar(select(func.count()).select_from(Transaction).where(Transaction.family_id==family_id,Transaction.custom_category_id==category_id)):return "in_use"
        await s.delete(cat);await s.commit();return "deleted"

async def detect_custom_category(family_id,title):
    text=title.lower().strip();best=None;score_best=0
    for cat in await list_custom_categories(family_id,True):
        score=sum(100 if text==k.normalized_keyword else 10 if k.normalized_keyword in text else 0 for k in cat.keywords)
        if score>score_best:best,score_best=cat,score
    return best,score_best
