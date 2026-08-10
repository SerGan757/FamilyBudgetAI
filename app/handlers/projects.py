from html import escape

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.handlers.project_states import ProjectState
from app.keyboards.projects import (
    ProjectCallback, project_back_keyboard, project_cancel_keyboard,
    project_card_keyboard, projects_keyboard,
)
from app.services.project_service import (
    DuplicateProjectTagError, create_project, get_project, get_project_card,
    get_project_transactions, list_projects, set_project_active,
    update_project_name, update_project_tag, validate_project_name,
    normalize_project_tag,
)
from app.services.settings_service import get_current_family_settings
from app.utils.currency import format_money
from app.i18n import normalize_language, t


router = Router()


def project_card_text(
    project, spent: float, operations: int, currency_code: str = "EUR", language: str = "ru",
) -> str:
    status = (
        f"🟢 {t(language, 'projects.active')}"
        if project.is_active else f"⚪ {t(language, 'projects.completed')}"
    )
    return (
        f"🏷 <b>{escape(project.name)}</b>\n\n"
        f"{t(language, 'projects.tag')}: #{escape(project.tag)}\n"
        f"{t(language, 'projects.status')}: {status}\n\n"
        f"{t(language, 'projects.spent')}: {format_money(spent, currency_code)}\n"
        f"{t(language, 'common.operations')}: {operations}"
    )


async def _show_projects(message, telegram_id: int, *, active: bool, page: int = 0):
    settings = await get_current_family_settings(telegram_id)
    language = normalize_language(settings.get("language") if settings else None)
    result = await list_projects(telegram_id, active=active, page=page)
    if result is None:
        await message.edit_text(t(language, "projects.user_not_found"))
        return
    projects, total = result
    title = f"🏷 <b>{t(language, 'projects.title')}</b>" if active else f"📦 <b>{t(language, 'projects.archive_title')}</b>"
    empty = t(language, "projects.active_empty") if active else t(language, "projects.archive_empty")
    text = title + ("\n\n" + empty if not projects else "")
    await message.edit_text(
        text, reply_markup=projects_keyboard(projects, total, page, active=active, language=language),
        parse_mode="HTML",
    )


async def _show_card(message, telegram_id: int, project_id: int, notice: str | None = None):
    settings = await get_current_family_settings(telegram_id)
    language = normalize_language(settings.get("language") if settings else None)
    result = await get_project_card(telegram_id, project_id)
    if result is None:
        await message.edit_text(t(language, "projects.not_found"))
        return
    project, spent, operations = result
    currency_code = settings["currency"] if settings else "EUR"
    text = project_card_text(project, spent, operations, currency_code, language)
    if notice:
        text = f"{notice}\n\n{text}"
    await message.edit_text(text, reply_markup=project_card_keyboard(project, language), parse_mode="HTML")


@router.callback_query(ProjectCallback.filter())
async def project_callback(
    callback: CallbackQuery, callback_data: ProjectCallback, state: FSMContext,
):
    message = callback.message
    if message is None:
        await callback.answer()
        return
    action = callback_data.action
    if action == "list":
        await state.clear()
        await _show_projects(message, callback.from_user.id, active=True, page=callback_data.page)
    elif action == "archive":
        await state.clear()
        await _show_projects(message, callback.from_user.id, active=False, page=callback_data.page)
    elif action == "settings":
        await state.clear()
        from app.handlers.settings import family_settings_text
        from app.keyboards.settings_menu import family_settings_keyboard_for_ttl
        data = await get_current_family_settings(callback.from_user.id)
        if data is None:
            await message.edit_text(t("ru", "projects.user_not_found"))
        else:
            await message.edit_text(
                family_settings_text(data),
                reply_markup=family_settings_keyboard_for_ttl(data["temporary_screen_ttl"], data["language"]),
                parse_mode="HTML",
            )
    elif action == "new":
        await state.clear()
        settings = await get_current_family_settings(callback.from_user.id)
        language = normalize_language(settings.get("language") if settings else None)
        await state.set_state(ProjectState.waiting_for_name)
        await message.edit_text(
            t(language, "projects.enter_name"), reply_markup=project_cancel_keyboard(language),
        )
    elif action == "cancel":
        await state.clear()
        await _show_projects(message, callback.from_user.id, active=True)
    elif action == "card":
        await state.clear()
        await _show_card(message, callback.from_user.id, callback_data.project_id)
    elif action in {"rename", "retag"}:
        settings = await get_current_family_settings(callback.from_user.id)
        language = normalize_language(settings.get("language") if settings else None)
        project = await get_project(callback.from_user.id, callback_data.project_id)
        if project is None:
            await callback.answer(t(language, "projects.not_found"), show_alert=True)
            return
        await state.clear()
        await state.update_data(project_id=project.id)
        if action == "rename":
            await state.set_state(ProjectState.waiting_for_rename)
            prompt = t(language, "projects.enter_new_name")
        else:
            await state.set_state(ProjectState.waiting_for_retag)
            prompt = t(language, "projects.enter_new_tag")
        await message.edit_text(prompt, reply_markup=project_cancel_keyboard(language))
    elif action == "toggle":
        settings = await get_current_family_settings(callback.from_user.id)
        language = normalize_language(settings.get("language") if settings else None)
        project = await get_project(callback.from_user.id, callback_data.project_id)
        if project is None:
            await callback.answer(t(language, "projects.not_found"), show_alert=True)
            return
        updated = await set_project_active(callback.from_user.id, project.id, not project.is_active)
        if updated is None:
            await callback.answer(t(language, "projects.not_found"), show_alert=True)
            return
        notice = t(language, "projects.reopened") if updated.is_active else t(language, "projects.finished")
        await _show_card(message, callback.from_user.id, updated.id, notice)
    elif action == "transactions":
        settings = await get_current_family_settings(callback.from_user.id)
        language = normalize_language(settings.get("language") if settings else None)
        result = await get_project_transactions(
            callback.from_user.id, callback_data.project_id, page=callback_data.page,
        )
        if result is None:
            await callback.answer(t(language, "projects.not_found"), show_alert=True)
            return
        transactions, total = result
        project = await get_project(callback.from_user.id, callback_data.project_id)
        currency_code = settings["currency"] if settings else "EUR"
        text = f"📊 <b>{t(language, 'projects.transactions_title')}: {escape(project.name)}</b>\n\n"
        if not transactions:
            text += t(language, "projects.no_transactions")
        for transaction in transactions:
            sign = "+" if transaction.type == "income" else "-"
            author = escape(transaction.user.name) if transaction.user else "—"
            text += (
                f"{transaction.created_at:%d.%m.%Y} · {escape(transaction.title)} · "
                f"{sign}{format_money(transaction.amount, currency_code)} · {author}\n"
            )
        keyboard = project_back_keyboard(project.id, language)
        if total > 10:
            from app.keyboards.projects import button
            rows = []
            nav = []
            if callback_data.page > 0:
                nav.append(button("⬅️", "transactions", project.id, callback_data.page - 1))
            if (callback_data.page + 1) * 10 < total:
                nav.append(button("➡️", "transactions", project.id, callback_data.page + 1))
            if nav:
                rows.append(nav)
            rows.extend(keyboard.inline_keyboard)
            keyboard = type(keyboard)(inline_keyboard=rows)
        await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        settings = await get_current_family_settings(callback.from_user.id)
        language = normalize_language(settings.get("language") if settings else None)
        await callback.answer(t(language, "projects.unknown"), show_alert=True)
        return
    await callback.answer()


@router.message(ProjectState.waiting_for_name)
async def project_name(message: Message, state: FSMContext):
    settings = await get_current_family_settings(message.from_user.id)
    language = normalize_language(settings.get("language") if settings else None)
    try:
        name = validate_project_name(message.text or "")
    except ValueError:
        await message.answer(
            t(language, "projects.invalid_name"),
            reply_markup=project_cancel_keyboard(language),
        )
        return
    await state.update_data(project_name=name)
    await state.set_state(ProjectState.waiting_for_tag)
    await message.answer(
        t(language, "projects.enter_tag"),
        reply_markup=project_cancel_keyboard(language),
    )


@router.message(ProjectState.waiting_for_tag)
async def project_tag(message: Message, state: FSMContext):
    data = await state.get_data()
    settings = await get_current_family_settings(message.from_user.id)
    language = normalize_language(settings.get("language") if settings else None)
    try:
        tag = normalize_project_tag(message.text or "")
    except ValueError:
        await message.answer(
            t(language, "projects.invalid_tag"),
            reply_markup=project_cancel_keyboard(language),
        )
        return
    try:
        project = await create_project(message.from_user.id, data.get("project_name", ""), tag)
    except DuplicateProjectTagError:
        await message.answer(
            t(language, "projects.duplicate_tag"),
            reply_markup=project_cancel_keyboard(language),
        )
        return
    if project is None:
        await state.clear()
        await message.answer(t(language, "projects.user_not_found"))
        return
    await state.clear()
    result = await get_project_card(message.from_user.id, project.id)
    project, spent, operations = result
    currency_code = settings["currency"] if settings else "EUR"
    await message.answer(
        t(language, "projects.created") + "\n\n" + project_card_text(project, spent, operations, currency_code, language),
        reply_markup=project_card_keyboard(project, language), parse_mode="HTML",
    )


async def _edit_project_value(message: Message, state: FSMContext, *, field: str):
    data = await state.get_data()
    project_id = data.get("project_id")
    settings = await get_current_family_settings(message.from_user.id)
    language = normalize_language(settings.get("language") if settings else None)
    try:
        if field == "name":
            updated = await update_project_name(message.from_user.id, project_id, message.text or "")
            notice = t(language, "projects.renamed")
        else:
            updated = await update_project_tag(message.from_user.id, project_id, message.text or "")
            notice = t(language, "projects.retagged")
    except DuplicateProjectTagError:
        await message.answer(
            t(language, "projects.duplicate_tag"),
            reply_markup=project_cancel_keyboard(language),
        )
        return
    except ValueError:
        await message.answer(
            t(language, "projects.invalid_edit"),
            reply_markup=project_cancel_keyboard(language),
        )
        return
    if updated is None:
        await state.clear()
        await message.answer(t(language, "projects.not_found"))
        return
    await state.clear()
    result = await get_project_card(message.from_user.id, updated.id)
    project, spent, operations = result
    currency_code = settings["currency"] if settings else "EUR"
    await message.answer(
        notice + "\n\n" + project_card_text(project, spent, operations, currency_code, language),
        reply_markup=project_card_keyboard(project, language), parse_mode="HTML",
    )


@router.message(ProjectState.waiting_for_rename)
async def rename_project(message: Message, state: FSMContext):
    await _edit_project_value(message, state, field="name")


@router.message(ProjectState.waiting_for_retag)
async def retag_project(message: Message, state: FSMContext):
    await _edit_project_value(message, state, field="tag")
