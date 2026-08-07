import logging
from html import escape

from aiogram import Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.exc import SQLAlchemyError

from app.keyboards.admin import (
    PAGE_SIZE, AdminCallback, admin_family_child_keyboard, admin_family_keyboard,
    admin_families_keyboard, admin_keyboard, admin_main_keyboard,
    admin_user_keyboard, admin_users_keyboard,
)
from app.services.admin_auth import is_admin
from app.services.admin_service import (
    get_admin_families_page, get_admin_family, get_admin_family_members,
    get_admin_family_statistics, get_admin_status, get_admin_user,
    get_admin_users_page,
)


logger = logging.getLogger(__name__)
router = Router(name="admin")
ADMIN_TITLE = "🛡 Админ-панель FamilyBudgetAI"
PRIVATE_ONLY_TEXT = "🔒 Админ-панель доступна только в личном чате с ботом."
ACCESS_DENIED_TEXT = "⛔ Доступ запрещён."
NOT_FOUND_TEXT = "Объект не найден."


def _message_is_private(message: Message) -> bool:
    return message.chat.type == ChatType.PRIVATE


async def _authorize_callback(callback: CallbackQuery) -> bool:
    message = callback.message
    if message is None or message.chat.type != ChatType.PRIVATE:
        await callback.answer(PRIVATE_ONLY_TEXT, show_alert=True)
        return False
    if not is_admin(callback.from_user.id):
        await callback.answer(ACCESS_DENIED_TEXT, show_alert=True)
        return False
    return True


def _money(value: int | float) -> str:
    return f"{float(value):.2f} €"


@router.message(Command("myid"))
async def my_id(message: Message) -> None:
    if message.from_user is not None:
        await message.answer(f"Ваш Telegram ID: {message.from_user.id}")


@router.message(Command("admin"))
async def open_admin(message: Message) -> None:
    if not _message_is_private(message):
        await message.answer(PRIVATE_ONLY_TEXT)
        return
    if message.from_user is None or not is_admin(message.from_user.id):
        await message.answer(ACCESS_DENIED_TEXT)
        return
    await message.answer(ADMIN_TITLE, reply_markup=admin_keyboard)


async def _show_admin_action(callback: CallbackQuery, data: AdminCallback) -> bool | None:
    action, object_id, page = data.action, data.object_id, max(data.page, 0)
    if action == "close":
        await callback.message.delete()
        return
    if action == "home":
        await callback.message.edit_text(ADMIN_TITLE, reply_markup=admin_main_keyboard())
        return
    if action == "status":
        status = await get_admin_status()
        body = (
            f"{ADMIN_TITLE}\n\n"
            f"База данных: <code>{escape(str(status['database']))}</code>\n"
            f"Семей: {status['families']}\nПользователей: {status['users']}\n"
            f"Транзакций: {status['transactions']}\n"
            f"Регулярных платежей: {status['recurring_payments']}"
        )
        await callback.message.edit_text(body, reply_markup=admin_main_keyboard(), parse_mode="HTML")
        return
    if action == "families":
        families, total = await get_admin_families_page(page, PAGE_SIZE)
        body = f"{ADMIN_TITLE}\n\n👨‍👩‍👧 Семьи" + ("" if families else "\n\nСемей пока нет.")
        await callback.message.edit_text(
            body, reply_markup=admin_families_keyboard(families, page, total), parse_mode="HTML",
        )
        return
    if action == "family":
        family = await get_admin_family(object_id)
        if family is None:
            await callback.answer(NOT_FOUND_TEXT, show_alert=True)
            return False
        body = (
            "👨‍👩‍👧 Семья\n\n"
            f"ID: {family['id']}\nНазвание: {escape(str(family['name']))}\n"
            f"Участников: {family['users']}\nОпераций: {family['transactions']}\n"
            f"Регулярных платежей: {family['recurring_payments']}"
        )
        await callback.message.edit_text(
            body, reply_markup=admin_family_keyboard(object_id, page), parse_mode="HTML",
        )
        return
    if action == "family_members":
        result = await get_admin_family_members(object_id)
        if result is None:
            await callback.answer(NOT_FOUND_TEXT, show_alert=True)
            return False
        family_name, members = result
        member_text = "\n".join(f"{index}. {escape(name)}" for index, name in enumerate(members, 1))
        body = f"👥 Участники: {escape(family_name)}\n\n" + (member_text or "Участников пока нет.")
        await callback.message.edit_text(
            body, reply_markup=admin_family_child_keyboard(object_id, page), parse_mode="HTML",
        )
        return
    if action == "family_stats":
        stats = await get_admin_family_statistics(object_id)
        if stats is None:
            await callback.answer(NOT_FOUND_TEXT, show_alert=True)
            return False
        body = (
            f"📊 Статистика семьи: {escape(str(stats['name']))}\n\n"
            f"Доходы за текущий месяц: {_money(stats['income'])}\n"
            f"Расходы за текущий месяц: {_money(stats['expense'])}\n"
            f"Баланс за текущий месяц: {_money(stats['balance'])}\n\n"
            f"Операций за текущий месяц: {stats['operations']}\n\n"
            f"Регулярных доходов: {_money(stats['recurring_income'])}/мес\n"
            f"Регулярных расходов: {_money(stats['recurring_expense'])}/мес"
        )
        await callback.message.edit_text(
            body, reply_markup=admin_family_child_keyboard(object_id, page), parse_mode="HTML",
        )
        return
    if action == "users":
        users, total = await get_admin_users_page(page, PAGE_SIZE)
        body = f"{ADMIN_TITLE}\n\n👤 Пользователи" + ("" if users else "\n\nПользователей пока нет.")
        await callback.message.edit_text(
            body, reply_markup=admin_users_keyboard(users, page, total), parse_mode="HTML",
        )
        return
    if action == "user":
        user = await get_admin_user(object_id)
        if user is None:
            await callback.answer(NOT_FOUND_TEXT, show_alert=True)
            return False
        body = (
            "👤 Пользователь\n\n"
            f"ID: {user['id']}\nИмя: {escape(str(user['name']))}\n"
            f"Семья: {escape(str(user['family_name']))}\n\n"
            f"Операций за текущий месяц: {user['operations']}\n"
            f"Доходы за текущий месяц: {_money(user['income'])}\n"
            f"Расходы за текущий месяц: {_money(user['expense'])}"
        )
        await callback.message.edit_text(
            body, reply_markup=admin_user_keyboard(page), parse_mode="HTML",
        )
        return
    await callback.answer("Неизвестное действие.", show_alert=True)
    return False


@router.callback_query(AdminCallback.filter())
async def admin_callback(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    if not await _authorize_callback(callback):
        return
    try:
        should_answer = await _show_admin_action(callback, callback_data)
    except SQLAlchemyError:
        logger.exception("Admin database operation failed")
        await callback.answer("Не удалось загрузить данные.", show_alert=True)
        return
    if should_answer is not False:
        await callback.answer()
