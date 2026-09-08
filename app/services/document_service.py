from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.database.db import SessionLocal
from app.database.models import Document, DocumentCategory, DocumentFile, User


DEFAULT_CATEGORIES = (
    ("personal", "👤"), ("family", "👨‍👩‍👧‍👦"),
    ("car", "🚗"), ("housing", "🏠"), ("germany", "🇩🇪"),
    ("medicine", "🩺"), ("work", "💼"), ("trips", "✈️"), ("other", "📁"),
)
ALLOWED_FILE_TYPES = {"photo", "document"}
ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


class DuplicateCategoryError(ValueError): pass
class CategoryNotEmptyError(ValueError): pass
class LastCategoryError(ValueError): pass
class InvalidDocumentFileError(ValueError): pass
class UploadSessionConflictError(ValueError): pass


@dataclass(frozen=True)
class DocumentFileResult:
    document: Document
    file: DocumentFile
    file_added: bool
    file_count: int


async def _user(session, telegram_id: int):
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


def validate_category_name(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 80:
        raise ValueError("Invalid category name")
    return value


def validate_title(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 150:
        raise ValueError("Invalid document title")
    return value


def _validate_document_file(data: dict) -> None:
    if data.get("file_type") not in ALLOWED_FILE_TYPES or (
        data.get("file_type") == "document"
        and data.get("mime_type") not in ALLOWED_MIME_TYPES
    ):
        raise InvalidDocumentFileError


async def ensure_default_categories(telegram_id: int):
    async with SessionLocal() as session:
        user = await _user(session, telegram_id)
        if user is None: return None
        existing = set((await session.execute(select(DocumentCategory.code).where(DocumentCategory.family_id == user.family_id, DocumentCategory.code.is_not(None)))).scalars())
        next_order = (await session.execute(select(func.coalesce(func.max(DocumentCategory.sort_order), -1)).where(DocumentCategory.family_id == user.family_id))).scalar_one() + 1
        for code, emoji in DEFAULT_CATEGORIES:
            if code not in existing:
                session.add(DocumentCategory(family_id=user.family_id, code=code, name=None, emoji=emoji, sort_order=next_order, is_system=True))
                next_order += 1
        try: await session.commit()
        except IntegrityError: await session.rollback()
        return await list_categories(telegram_id)


async def list_categories(telegram_id: int, active: bool = True):
    async with SessionLocal() as session:
        user = await _user(session, telegram_id)
        if user is None: return None
        result = await session.execute(select(DocumentCategory).where(DocumentCategory.family_id == user.family_id, DocumentCategory.is_active.is_(active)).order_by(DocumentCategory.sort_order, DocumentCategory.id))
        return result.scalars().all()


async def get_category(telegram_id: int, category_id: int):
    async with SessionLocal() as session:
        user = await _user(session, telegram_id)
        if user is None: return None
        return (await session.execute(select(DocumentCategory).where(DocumentCategory.id == category_id, DocumentCategory.family_id == user.family_id))).scalar_one_or_none()


async def create_category(telegram_id: int, name: str, emoji: str):
    name = validate_category_name(name)
    async with SessionLocal() as session:
        user = await _user(session, telegram_id)
        if user is None: return None
        order = (await session.execute(select(func.coalesce(func.max(DocumentCategory.sort_order), -1)).where(DocumentCategory.family_id == user.family_id))).scalar_one() + 1
        item = DocumentCategory(family_id=user.family_id, name=name, emoji=emoji, sort_order=order)
        session.add(item)
        try: await session.commit()
        except IntegrityError as exc:
            await session.rollback(); raise DuplicateCategoryError(name) from exc
        await session.refresh(item); return item


async def update_category(telegram_id: int, category_id: int, **values):
    async with SessionLocal() as session:
        user = await _user(session, telegram_id)
        if user is None: return None
        item = (await session.execute(select(DocumentCategory).where(DocumentCategory.id == category_id, DocumentCategory.family_id == user.family_id))).scalar_one_or_none()
        if item is None: return None
        if "name" in values: values["name"] = validate_category_name(values["name"])
        for key in ("name", "emoji", "is_active"):
            if key in values: setattr(item, key, values[key])
        try: await session.commit()
        except IntegrityError as exc:
            await session.rollback(); raise DuplicateCategoryError(values.get("name", "")) from exc
        await session.refresh(item); return item


async def move_category(telegram_id: int, category_id: int, direction: int):
    categories = await list_categories(telegram_id, active=True)
    if categories is None: return None
    index = next((i for i, value in enumerate(categories) if value.id == category_id), None)
    target = index + direction if index is not None else -1
    if index is None or target < 0 or target >= len(categories): return categories[index] if index is not None else None
    async with SessionLocal() as session:
        user = await _user(session, telegram_id)
        current = await session.get(DocumentCategory, categories[index].id)
        other = await session.get(DocumentCategory, categories[target].id)
        if not user or current.family_id != user.family_id or other.family_id != user.family_id: return None
        current.sort_order, other.sort_order = other.sort_order, current.sort_order
        await session.commit(); await session.refresh(current); return current


async def delete_category(telegram_id: int, category_id: int):
    async with SessionLocal() as session:
        user = await _user(session, telegram_id)
        if user is None: return False
        item = (await session.execute(select(DocumentCategory).where(DocumentCategory.id == category_id, DocumentCategory.family_id == user.family_id))).scalar_one_or_none()
        if item is None: return False
        count = (await session.execute(select(func.count(Document.id)).where(Document.category_id == item.id, Document.family_id == user.family_id))).scalar_one()
        if count: raise CategoryNotEmptyError
        active_count = (await session.execute(select(func.count(DocumentCategory.id)).where(DocumentCategory.family_id == user.family_id, DocumentCategory.is_active.is_(True)))).scalar_one()
        if item.is_active and active_count <= 1: raise LastCategoryError
        await session.delete(item); await session.commit(); return True


async def list_documents(telegram_id: int, category_id: int | None = None):
    async with SessionLocal() as session:
        user = await _user(session, telegram_id)
        if user is None: return None
        filters = [Document.family_id == user.family_id, or_(Document.access_level == "family", Document.created_by_user_id == user.id)]
        if category_id is not None: filters.append(Document.category_id == category_id)
        result = await session.execute(select(Document).options(selectinload(Document.files), selectinload(Document.category)).where(*filters).order_by(Document.created_at.desc(), Document.id.desc()))
        return result.scalars().all()


async def create_or_append_document_file(
    telegram_id: int,
    upload_session_key: str,
    category_id: int,
    title: str,
    owner_name: str | None,
    access_level: str,
    data: dict,
) -> DocumentFileResult | None:
    title = validate_title(title)
    owner_name = owner_name or None
    if not upload_session_key or len(upload_session_key) > 36:
        raise ValueError("Invalid upload session")
    if access_level not in {"family", "private"}:
        raise ValueError("Invalid document")
    _validate_document_file(data)

    async with SessionLocal() as session:
        user = await _user(session, telegram_id)
        if user is None:
            return None

        category = (await session.execute(select(DocumentCategory).where(
            DocumentCategory.id == category_id,
            DocumentCategory.family_id == user.family_id,
            DocumentCategory.is_active.is_(True),
        ))).scalar_one_or_none()
        if category is None:
            return None

        insert_document = postgresql_insert(Document).values(
            family_id=user.family_id,
            category_id=category.id,
            title=title,
            owner_name=owner_name,
            access_level=access_level,
            created_by_user_id=user.id,
            upload_session_key=upload_session_key,
        ).on_conflict_do_nothing(
            index_elements=[Document.upload_session_key],
            index_where=Document.upload_session_key.is_not(None),
        )
        await session.execute(insert_document)

        document = (await session.execute(select(Document).where(
            Document.upload_session_key == upload_session_key,
            Document.family_id == user.family_id,
            Document.created_by_user_id == user.id,
        ).with_for_update())).scalar_one_or_none()
        if document is None:
            return None

        if (
            document.category_id != category.id
            or document.title != title
            or document.owner_name != owner_name
            or document.access_level != access_level
        ):
            raise UploadSessionConflictError(upload_session_key)

        existing_file = (await session.execute(select(DocumentFile).where(
            DocumentFile.document_id == document.id,
            DocumentFile.telegram_file_unique_id == data.get("telegram_file_unique_id"),
            DocumentFile.telegram_file_unique_id.is_not(None),
        ))).scalar_one_or_none()
        if existing_file is not None:
            file_count = (await session.execute(select(func.count(DocumentFile.id)).where(
                DocumentFile.document_id == document.id,
            ))).scalar_one()
            await session.commit()
            loaded = await get_document(telegram_id, document.id)
            return DocumentFileResult(loaded, existing_file, False, file_count)

        next_order = (await session.execute(select(
            func.coalesce(func.max(DocumentFile.sort_order), -1),
        ).where(DocumentFile.document_id == document.id))).scalar_one() + 1
        document_file = DocumentFile(
            document_id=document.id, sort_order=next_order, **data,
        )
        session.add(document_file)
        await session.flush()
        file_count = (await session.execute(select(func.count(DocumentFile.id)).where(
            DocumentFile.document_id == document.id,
        ))).scalar_one()
        await session.commit()
        loaded = await get_document(telegram_id, document.id)
        return DocumentFileResult(loaded, document_file, True, file_count)


async def get_document(telegram_id: int, document_id: int):
    async with SessionLocal() as session:
        user = await _user(session, telegram_id)
        if user is None: return None
        result = await session.execute(select(Document).options(selectinload(Document.files), selectinload(Document.category)).where(Document.id == document_id, Document.family_id == user.family_id, or_(Document.access_level == "family", Document.created_by_user_id == user.id)))
        return result.scalar_one_or_none()


async def search_documents(telegram_id: int, query: str):
    query = query.strip()
    if not query: return []
    async with SessionLocal() as session:
        user = await _user(session, telegram_id)
        if user is None: return None
        result = await session.execute(select(Document).where(Document.family_id == user.family_id, Document.title.ilike(f"%{query}%"), or_(Document.access_level == "family", Document.created_by_user_id == user.id)).order_by(Document.title, Document.id))
        return result.scalars().all()


async def delete_document(telegram_id: int, document_id: int):
    async with SessionLocal() as session:
        user = await _user(session, telegram_id)
        if user is None: return False
        document = (await session.execute(select(Document).where(Document.id == document_id, Document.family_id == user.family_id, Document.created_by_user_id == user.id))).scalar_one_or_none()
        if document is None: return False
        await session.delete(document); await session.commit(); return True
