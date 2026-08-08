from difflib import SequenceMatcher
import re

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.database.db import SessionLocal
from app.database.models import Project, Transaction, User
from app.services.family_activity_service import touch_family_activity


class DuplicateProjectTagError(ValueError):
    pass


PROJECT_TAG_AT_END = re.compile(r"(?<!\S)#([^\s#]+)\s*$", re.UNICODE)


def extract_project_tag(text: str) -> tuple[str, str | None]:
    match = PROJECT_TAG_AT_END.search(text)
    if match is None:
        return text, None
    if text.count("#") != 1:
        raise ValueError("Only one project tag is supported")
    tag = normalize_project_tag(match.group(1))
    cleaned = text[:match.start()].rstrip()
    if not cleaned:
        raise ValueError("Transaction text is empty")
    return cleaned, tag


def validate_project_name(value: str) -> str:
    name = value.strip()
    if not name or len(name) > 100 or name.startswith("/"):
        raise ValueError("Invalid project name")
    return name


def normalize_project_tag(value: str) -> str:
    tag = value.strip()
    if tag.startswith("#"):
        tag = tag[1:]
    tag = tag.casefold()
    if not 2 <= len(tag) <= 30 or not tag.isalnum():
        raise ValueError("Invalid project tag")
    return tag


async def _current_family_id(session, telegram_id: int) -> int | None:
    result = await session.execute(select(User.family_id).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def list_projects(
    telegram_id: int, *, active: bool, page: int = 0, page_size: int = 10,
):
    page = max(page, 0)
    async with SessionLocal() as session:
        family_id = await _current_family_id(session, telegram_id)
        if family_id is None:
            return None
        filters = (Project.family_id == family_id, Project.is_active.is_(active))
        count = await session.execute(select(func.count(Project.id)).where(*filters))
        result = await session.execute(
            select(Project).where(*filters).order_by(Project.name, Project.id)
            .offset(page * page_size).limit(page_size)
        )
        return result.scalars().all(), count.scalar_one()


async def get_project(telegram_id: int, project_id: int):
    async with SessionLocal() as session:
        family_id = await _current_family_id(session, telegram_id)
        if family_id is None:
            return None
        result = await session.execute(
            select(Project).where(Project.id == project_id, Project.family_id == family_id)
        )
        return result.scalar_one_or_none()


async def create_project(telegram_id: int, name: str, tag: str):
    name = validate_project_name(name)
    tag = normalize_project_tag(tag)
    async with SessionLocal() as session:
        family_id = await _current_family_id(session, telegram_id)
        if family_id is None:
            return None
        project = Project(family_id=family_id, name=name, tag=tag)
        session.add(project)
        await touch_family_activity(family_id, session=session)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise DuplicateProjectTagError(tag) from exc
        await session.refresh(project)
        return project


async def update_project_name(telegram_id: int, project_id: int, name: str):
    name = validate_project_name(name)
    return await _update_project(telegram_id, project_id, name=name)


async def update_project_tag(telegram_id: int, project_id: int, tag: str):
    tag = normalize_project_tag(tag)
    try:
        return await _update_project(telegram_id, project_id, tag=tag)
    except IntegrityError as exc:
        raise DuplicateProjectTagError(tag) from exc


async def set_project_active(telegram_id: int, project_id: int, active: bool):
    return await _update_project(telegram_id, project_id, is_active=active)


async def _update_project(telegram_id: int, project_id: int, **values):
    async with SessionLocal() as session:
        family_id = await _current_family_id(session, telegram_id)
        if family_id is None:
            return None
        result = await session.execute(
            select(Project).where(Project.id == project_id, Project.family_id == family_id)
        )
        project = result.scalar_one_or_none()
        if project is None:
            return None
        for field, value in values.items():
            setattr(project, field, value)
        await touch_family_activity(family_id, session=session)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise
        await session.refresh(project)
        return project


async def get_project_card(telegram_id: int, project_id: int):
    async with SessionLocal() as session:
        family_id = await _current_family_id(session, telegram_id)
        if family_id is None:
            return None
        project_result = await session.execute(
            select(Project).where(Project.id == project_id, Project.family_id == family_id)
        )
        project = project_result.scalar_one_or_none()
        if project is None:
            return None
        stats = await session.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0.0), func.count(Transaction.id))
            .where(
                Transaction.family_id == family_id,
                Transaction.project_id == project.id,
                Transaction.type == "expense",
            )
        )
        spent, operations = stats.one()
        return project, float(spent), int(operations)


async def get_project_transactions(
    telegram_id: int, project_id: int, *, page: int = 0, page_size: int = 10,
):
    page = max(page, 0)
    async with SessionLocal() as session:
        family_id = await _current_family_id(session, telegram_id)
        if family_id is None:
            return None
        project = await session.execute(
            select(Project).where(Project.id == project_id, Project.family_id == family_id)
        )
        if project.scalar_one_or_none() is None:
            return None
        filters = (Transaction.family_id == family_id, Transaction.project_id == project_id)
        count = await session.execute(select(func.count(Transaction.id)).where(*filters))
        result = await session.execute(
            select(Transaction).options(selectinload(Transaction.user)).where(*filters)
            .order_by(Transaction.created_at.desc(), Transaction.id.desc())
            .offset(page * page_size).limit(page_size)
        )
        return result.scalars().all(), count.scalar_one()


async def find_family_project_by_tag(family_id: int, tag: str):
    tag = normalize_project_tag(tag)
    async with SessionLocal() as session:
        result = await session.execute(
            select(Project).where(Project.family_id == family_id, Project.tag == tag)
        )
        return result.scalar_one_or_none()


async def suggest_active_family_project(family_id: int, tag: str):
    tag = normalize_project_tag(tag)
    async with SessionLocal() as session:
        result = await session.execute(
            select(Project).where(Project.family_id == family_id, Project.is_active.is_(True))
        )
        ranked = sorted(
            ((SequenceMatcher(None, tag, project.tag).ratio(), project) for project in result.scalars()),
            key=lambda item: item[0], reverse=True,
        )
        if not ranked or ranked[0][0] < 0.6:
            return None
        if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
            return None
        return ranked[0][1]
