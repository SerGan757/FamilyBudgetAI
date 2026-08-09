from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.i18n import t


class ProjectCallback(CallbackData, prefix="project"):
    action: str
    project_id: int = 0
    page: int = 0


class PendingProjectCallback(CallbackData, prefix="pending_project"):
    action: str
    project_id: int = 0


def button(text: str, action: str, project_id: int = 0, page: int = 0):
    return InlineKeyboardButton(
        text=text,
        callback_data=ProjectCallback(
            action=action, project_id=project_id, page=page,
        ).pack(),
    )


def projects_keyboard(projects, total: int, page: int, *, active: bool, language: str = "ru"):
    rows = [
        [button(f"🏷 {project.name} — #{project.tag}", "card", project.id, page)]
        for project in projects
    ]
    navigation = []
    if page > 0:
        navigation.append(button("⬅️", "list" if active else "archive", page=page - 1))
    if (page + 1) * 10 < total:
        navigation.append(button("➡️", "list" if active else "archive", page=page + 1))
    if navigation:
        rows.append(navigation)
    if active:
        rows.extend([
            [button(t(language, "projects.new"), "new")],
            [button(t(language, "projects.archive"), "archive")],
        ])
    else:
        rows.append([button("⬅️ К активным", "list")])
    rows.append([button(t(language, "nav.back"), "settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def project_card_keyboard(project, language: str = "ru"):
    rows = [
        [button(f"✏️ {t(language, 'projects.name')}", "rename", project.id)],
        [button(f"✏️ {t(language, 'projects.tag')}", "retag", project.id)],
        [button(t(language, "projects.transactions"), "transactions", project.id)],
        [button(t(language, "projects.finish") if project.is_active else t(language, "projects.resume"), "toggle", project.id)],
        [button("⬅️ К проектам", "list" if project.is_active else "archive")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def project_back_keyboard(project_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [button("⬅️ К проекту", "card", project_id)],
        [button("⬅️ К проектам", "list")],
    ])


def project_cancel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[button("❌ Отмена", "cancel")]])


def pending_project_keyboard(suggested_project=None):
    rows = []
    if suggested_project is not None:
        rows.append([InlineKeyboardButton(
            text=f"✅ {suggested_project.name}",
            callback_data=PendingProjectCallback(
                action="select", project_id=suggested_project.id,
            ).pack(),
        )])
    rows.extend([
        [InlineKeyboardButton(
            text="Без проекта",
            callback_data=PendingProjectCallback(action="without").pack(),
        )],
        [InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=PendingProjectCallback(action="cancel").pack(),
        )],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)
