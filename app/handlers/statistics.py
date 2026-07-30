from datetime import date, timedelta
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyKeyboardRemove

from app.keyboards.pagination_keyboard import pagination_keyboard
from app.services.statistics_service import (
    get_analytics,
    get_balance,
    get_month_statistics,
    get_today_statistics,
)
from app.services.user_service import get_user_by_telegram_id
from app.keyboards.main_menu import back_to_main_menu_keyboard

router = Router()

LIMIT = 20


def money(value: float) -> str:
    return f"{value:,.2f} €".replace(",", " ")


def format_transaction(transaction):

    sign = "+" if transaction.type == "income" else "-"

    amount = abs(transaction.amount)

    if amount.is_integer():
        amount_text = f"{sign}{int(amount)} €"
    else:
        amount_text = f"{sign}{amount:.2f} €"

    if transaction.is_recurring:
        amount_text += "/мес"

    base_icon = "💰" if transaction.type == "income" else escape(transaction.category.split()[0])
    icon = f"🔁 {base_icon}" if transaction.is_recurring else base_icon

    author = (
        escape(transaction.user.name)
        if getattr(transaction, "user", None)
        else ""
    )[:3]

    title = escape(transaction.title)

    if len(title) > 18:
        title = title[:17] + "…"

    return (
        f"{transaction.id} "
        f"{icon} "
        f"{title} "
        f"{amount_text} "
        f"{author}"
    )


def format_today(
    data,
    selected_date: date,
    offset: int = 0,
):

    text = (
        f"📅 <b>{selected_date.strftime('%d.%m.%Y')}</b>\n\n"
        f"💰 Доходы     {money(data['income'])}\n"
        f"💸 Расходы    {money(data['expense'])}\n"
        f"📈 Баланс     {money(data['balance'])}\n"
    )

    text += "\n"

    regular = data["transactions"]

    total = data["total"]
    if not regular:

        text += "Операций нет."

    else:

        for transaction in regular:

            text += (
                format_transaction(transaction)
                + "\n"
            )

    shown = min(
        offset + LIMIT,
        total,
    )

    text += (
        f"\n<b>Показано: {shown} из {total}</b>"
    )

    return text


@router.message(Command("today"))
async def today(message: Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if user is None:
        return

    selected_date = date.today()
    data = await get_today_statistics(
        user.family_id,
        selected_date=selected_date,
        offset=0,
        limit=LIMIT,
    )

    total = data["total"]

    await message.answer(
        format_today(
            data,
            selected_date,
            offset=0,
        ),
        parse_mode="HTML",
        reply_markup=day_keyboard(selected_date, 0, total),
    )  


@router.callback_query(F.data.startswith("today:") | F.data.startswith("day:"))
async def today_page(
    callback: CallbackQuery,
):

    parts = callback.data.split(":")
    try:
        if parts[0] == "day":
            selected_date, offset = date.fromisoformat(parts[1]), 0
        else:
            selected_date, offset = date.fromisoformat(parts[1]), int(parts[3])
    except (IndexError, ValueError):
        await callback.answer("Некорректная дата", show_alert=True)
        return

    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    data = await get_today_statistics(
        user.family_id,
        selected_date=selected_date,
        offset=offset,
        limit=LIMIT,
    )

    total = data["total"]
   

    await callback.message.edit_text(
        format_today(
            data,
            selected_date,
            offset=offset,
        ),
        parse_mode="HTML",
        reply_markup=day_keyboard(selected_date, offset, total),
    )

    await callback.answer()


def format_month(
    data,
    year: int,
    month: int,
    offset: int = 0,
):

    months = [
        "",
        "Январь",
        "Февраль",
        "Март",
        "Апрель",
        "Май",
        "Июнь",
        "Июль",
        "Август",
        "Сентябрь",
        "Октябрь",
        "Ноябрь",
        "Декабрь",
    ]

    text = (
        f"📅 <b>{months[month]} {year}</b>\n\n"
        f"💰 Доходы: {money(data['ordinary_income'])}\n"
        f"💸 Расходы: {money(data['ordinary_expense'])}\n\n"
        f"🔁 Регулярные расходы: {data['recurring_expense']:.2f} €/мес ({data['recurring_expense_count']})\n"
        f"🔁 Регулярные доходы: {data['recurring_income']:.2f} €/мес ({data['recurring_income_count']})\n\n"
        f"📈 Баланс: {money(data['balance'])}\n\n"
    )

    regular = data["transactions"]

    total = data["total"]

    if not regular:

        text += "Операций за этот месяц нет."

    else:

        for transaction in regular:

            text += (
                format_transaction(transaction)
                + "\n"
            )

    shown = min(
        offset + LIMIT,
        total,
    )

    text += (
        f"\n<b>Показано: {shown} из {total}</b>"
    )

    return text


def day_keyboard(selected_date: date, offset: int, total: int) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(text="⬅️ Предыдущий день", callback_data=f"day:{(selected_date - timedelta(days=1)).isoformat()}"),
        InlineKeyboardButton(text="➡️ Следующий день", callback_data=f"day:{(selected_date + timedelta(days=1)).isoformat()}"),
    ]]
    page = []
    if offset > 0:
        page.append(InlineKeyboardButton(text="⬅️ Предыдущие 20", callback_data=f"today:{selected_date.isoformat()}:page:{max(0, offset-LIMIT)}"))
    if offset + LIMIT < total:
        page.append(InlineKeyboardButton(text="➡️ Следующие 20", callback_data=f"today:{selected_date.isoformat()}:page:{offset+LIMIT}"))
    if page:
        rows.append(page)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + month - 1 + delta
    return index // 12, index % 12 + 1


def month_keyboard(year: int, month: int, offset: int, total: int) -> InlineKeyboardMarkup:
    previous_year, previous_month = _shift_month(year, month, -1)
    next_year, next_month = _shift_month(year, month, 1)
    rows = [[
        InlineKeyboardButton(text="⬅️ Предыдущий месяц", callback_data=f"month:{previous_year}:{previous_month:02d}"),
        InlineKeyboardButton(text="➡️ Следующий месяц", callback_data=f"month:{next_year}:{next_month:02d}"),
    ]]
    page = []
    if offset > 0:
        page.append(InlineKeyboardButton(text="⬅️ Предыдущие 20", callback_data=f"month:{year}:{month:02d}:{max(0, offset-LIMIT)}"))
    if offset + LIMIT < total:
        page.append(InlineKeyboardButton(text="➡️ Следующие 20", callback_data=f"month:{year}:{month:02d}:{offset+LIMIT}"))
    if page:
        rows.append(page)
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("month"))
async def month(message: Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if user is None:
        return

    today = date.today()
    data = await get_month_statistics(
        user.family_id,
        year=today.year,
        month=today.month,
        offset=0,
        limit=LIMIT,
    )

    total = data["total"]
   

    await message.answer(
        format_month(
            data,
            today.year,
            today.month,
            offset=0,
        ),
        parse_mode="HTML",
        reply_markup=month_keyboard(today.year, today.month, 0, total),
    )


@router.callback_query(
    F.data.startswith("month:")
)
async def month_page(
    callback: CallbackQuery,
):

    parts = callback.data.split(":")
    if len(parts) not in (3, 4):
        await callback.answer("Некорректный месяц", show_alert=True)
        return
    year, month = int(parts[1]), int(parts[2])
    offset = int(parts[3]) if len(parts) == 4 else 0
    if not 1 <= month <= 12:
        await callback.answer("Некорректный месяц", show_alert=True)
        return

    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    data = await get_month_statistics(
        user.family_id,
        year=year,
        month=month,
        offset=offset,
        limit=LIMIT,
    )

    total = data["total"]

    await callback.message.edit_text(
        format_month(
            data,
            year,
            month,
            offset=offset,
        ),
        parse_mode="HTML",
        reply_markup=month_keyboard(year, month, offset, total),
    )

    await callback.answer()


@router.message(Command("balance"))
async def balance(message: Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if user is None:
        return

    data = await get_balance(user.family_id)

    text = (
        f"<b>💰 ТЕКУЩИЙ БАЛАНС</b>\n\n"
        f"💰 Доходы: {money(data['ordinary_income'])}\n"
        f"💸 Расходы: {money(data['ordinary_expense'])}\n\n"
        f"🔁 Регулярные расходы: {data['recurring_expense']:.2f} €/мес ({data['recurring_expense_count']})\n"
        f"🔁 Регулярные доходы: {data['recurring_income']:.2f} €/мес ({data['recurring_income_count']})\n\n"
        f"<b>💎 Остаток     : {money(data['balance'])}</b>"
    )

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=back_to_main_menu_keyboard,
    )


@router.message(Command("analytics"))
async def analytics(message: Message, year: int | None = None, month: int | None = None, family_id: int | None = None):
    if family_id is None:
        user = await get_user_by_telegram_id(message.from_user.id)
        if user is None:
            return
        family_id = user.family_id

    months = [
        "",
        "Январь",
        "Февраль",
        "Март",
        "Апрель",
        "Май",
        "Июнь",
        "Июль",
        "Август",
        "Сентябрь",
        "Октябрь",
        "Ноябрь",
        "Декабрь",
    ]

    today = date.today()
    year, month = year or today.year, month or today.month
    data = await get_analytics(family_id, year, month)

    text = (
        f"📊 <b>Аналитика • {months[month]} {year}</b>\n\n"

        f"💰 Обычные доходы: <b>{money(data['ordinary_income'])}</b>\n"
        f"💸 Обычные расходы: <b>{money(data['ordinary_expense'])}</b>\n\n"
        f"🔁 Регулярные доходы: <b>{money(data['recurring_income'])}/мес ({data['recurring_income_count']})</b>\n"
        f"🔁 Регулярные расходы: <b>{money(data['recurring_expense'])}/мес ({data['recurring_expense_count']})</b>\n\n"
        f"💎 Остаток месяца: <b>{money(data['balance'])}</b>\n\n"

        f"📋 Операций: <b>{data['operations']}</b>\n"
        f"🧾 Средний чек: <b>{money(data['average_check'])}</b>\n"
        f"📅 В день: <b>{money(data['average_day'])}</b>\n"
    )
    if data["users"]:

        text += "\n👨 <b>Расходы участников</b>\n"

        medals = [
            "🥇",
            "🥈",
            "🥉",
        ]

        for i, (name, amount) in enumerate(data["users"][:5]):

            medal = medals[i] if i < len(medals) else "▪️"

            text += (
                f"{medal} {escape(name)} — <b>{money(amount)}</b>\n"
            )

    if data["categories"]:

        text += "\n🏆 <b>Категории</b>\n"

        for i, (category, amount) in enumerate(data["categories"][:5], 1):

            text += (
                f"{i}. {escape(category)} — <b>{money(amount)}</b>\n"
            )

    if data["biggest"]:

        purchase = data["biggest"]

        purchase_date = purchase.created_at.strftime("%d.%m")

        text += (
            "\n🔥 <b>Крупнейшая покупка</b>\n"
            f"{purchase_date} • {escape(purchase.title)}\n"
            f"<b>{money(purchase.amount)}</b>"
        )

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=analytics_keyboard(year, month),
    )


def analytics_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    previous_year, previous_month = _shift_month(year, month, -1)
    next_year, next_month = _shift_month(year, month, 1)
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Предыдущий месяц", callback_data=f"analytics:{previous_year}:{previous_month:02d}"),
        InlineKeyboardButton(text="➡️ Следующий месяц", callback_data=f"analytics:{next_year}:{next_month:02d}"),
    ]])


@router.callback_query(F.data.startswith("analytics:"))
async def analytics_page(callback: CallbackQuery):
    try:
        _, year, month = callback.data.split(":")
        year, month = int(year), int(month)
        if not 1 <= month <= 12:
            raise ValueError
    except ValueError:
        await callback.answer("Некорректный месяц", show_alert=True)
        return
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    await analytics(callback.message, year, month, user.family_id)
    await callback.answer()
