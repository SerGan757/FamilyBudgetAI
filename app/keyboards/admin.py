from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


PAGE_SIZE = 10


class AdminCallback(CallbackData, prefix="admin"):
    action: str
    object_id: int = 0
    page: int = 0


def _button(text: str, action: str, *, object_id: int = 0, page: int = 0) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=AdminCallback(action=action, object_id=object_id, page=page).pack(),
    )


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_button("📊 Статус", "status")],
        [_button("👨‍👩‍👧 Семьи", "families")],
        [_button("👤 Пользователи", "users")],
        [_button("❌ Закрыть", "close")],
    ])


admin_keyboard = admin_main_keyboard()


def _pagination(action: str, page: int, total: int) -> list[InlineKeyboardButton]:
    buttons = []
    if page > 0:
        buttons.append(_button("⬅️", action, page=page - 1))
    if (page + 1) * PAGE_SIZE < total:
        buttons.append(_button("➡️", action, page=page + 1))
    return buttons


def admin_families_keyboard(items: list[tuple[int, str]], page: int, total: int) -> InlineKeyboardMarkup:
    rows = [[_button(f"👨‍👩‍👧 {name}", "family", object_id=family_id, page=page)]
            for family_id, name in items]
    if navigation := _pagination("families", page, total):
        rows.append(navigation)
    rows.append([_button("⬅️ Назад", "home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_family_keyboard(family_id: int, page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_button("👥 Участники", "family_members", object_id=family_id, page=page)],
        [_button("📊 Статистика", "family_stats", object_id=family_id, page=page)],
        [_button("⬅️ К семьям", "families", page=page)],
        [_button("🏠 Админ-панель", "home")],
    ])


def admin_family_child_keyboard(family_id: int, page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_button("⬅️ К семье", "family", object_id=family_id, page=page)],
        [_button("🏠 Админ-панель", "home")],
    ])


def admin_users_keyboard(items: list[tuple[int, str]], page: int, total: int) -> InlineKeyboardMarkup:
    rows = [[_button(f"👤 {name}", "user", object_id=user_id, page=page)]
            for user_id, name in items]
    if navigation := _pagination("users", page, total):
        rows.append(navigation)
    rows.append([_button("⬅️ Назад", "home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_user_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_button("⬅️ К пользователям", "users", page=page)],
        [_button("🏠 Админ-панель", "home")],
    ])
