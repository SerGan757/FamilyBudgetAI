from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.keyboards.pagination_keyboard import pagination_keyboard
from app.services.statistics_service import (
    get_analytics,
    get_balance,
    get_month_statistics,
    get_today_statistics,
)

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

    if transaction.type == "income":
        icon = "💰"
    elif transaction.is_recurring:
        icon = "🔁"
    else:
        icon = transaction.category.split()[0]

    author = (
        transaction.user.name
        if getattr(transaction, "user", None)
        else ""
    )[:3]

    title = transaction.title

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
    offset: int = 0,
):

    text = (
        f"📅 <b>{date.today().strftime('%d.%m.%Y')}</b>\n\n"
        f"💰 Доходы     {money(data['income'])}\n"
        f"💸 Расходы    {money(data['expense'])}\n"
        f"📈 Баланс     {money(data['balance'])}\n"
    )

    if data["recurring_count"] > 0:

        text += "\n📋 <b>Операции</b>\n\n"

    text += (
        "\n📋 <b>Операции</b>\n\n"
        "<code>"
        "ID  Операция             Сумма      Имя"
        "</code>\n\n"
    )

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

    data = await get_today_statistics(
        offset=0,
        limit=LIMIT,
    )

    total = data["total"]

    await message.answer(
        format_today(
            data,
            offset=0,
        ),
        parse_mode="HTML",
        reply_markup=pagination_keyboard(
            prefix="today",
            offset=0,
            total=total,
            limit=LIMIT,
        ),
    )  


@router.callback_query(
    F.data.startswith("today:")
)
async def today_page(
    callback: CallbackQuery,
):

    offset = int(
        callback.data.split(":")[1]
    )

    data = await get_today_statistics(
    offset=offset,
    limit=LIMIT,
    )

    total = data["total"]
   

    await callback.message.edit_text(
        format_today(
            data,
            offset=offset,
        ),
        parse_mode="HTML",
        reply_markup=pagination_keyboard(
            offset=offset,
            total=total,
            limit=LIMIT,
            prefix="today"
        ),
    )

    await callback.answer()


def format_month(
    data,
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

    today = date.today()

    text = (
        f"📅 <b>{months[today.month]} {today.year}</b>\n\n"
        f"💰 Доходы     {money(data['income'])}\n"
        f"💸 Расходы    {money(data['expense'])}\n"
        f"📈 Баланс     {money(data['balance'])}\n"
    )

    if data["recurring_count"] > 0:

        text += (
            f"\n<b>🔁 Регулярные: "
            f"{data['recurring']:.2f} €/мес "
            f"({data['recurring_count']})</b>\n"
        )

    text += "\n📋 <b>Операции</b>\n\n"

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


@router.message(Command("month"))
async def month(message: Message):

    data = await get_month_statistics(
        offset=0,
        limit=LIMIT,
    )

    total = data["total"]
   

    await message.answer(
        format_month(
            data,
            offset=0,
        ),
        parse_mode="HTML",
        reply_markup=pagination_keyboard(
            prefix="month",
            offset=0,
            total=total,
            limit=LIMIT,
        ),
    )


@router.callback_query(
    F.data.startswith("month:")
)
async def month_page(
    callback: CallbackQuery,
):

    offset = int(
        callback.data.split(":")[1]
    )

    data = await get_month_statistics(
        offset=offset,
        limit=LIMIT,
    )

    total = data["total"]

    await callback.message.edit_text(
        format_month(
            data,
            offset=offset,
        ),
        parse_mode="HTML",
        reply_markup=pagination_keyboard(
            offset=offset,
            total=total,
            limit=LIMIT,
            prefix="month"
        ),
    )

    await callback.answer()


@router.message(Command("balance"))
async def balance(message: Message):

    data = await get_balance()

    text = (
        f"<b>💰 ОБЩИЙ БАЛАНС</b>\n"
        f"══════════════════════\n\n"
        f"💰 Доходы      : {money(data['income'])}\n"
        f"💸 Расходы     : {money(data['expense'])}\n"
        f"<b>🔁 Регулярные : {data['recurring']:.2f} €/мес ({data['recurring_count']})</b>\n"
        f"──────────────────────\n"
        f"<b>💎 Остаток     : {money(data['balance'])}</b>"
    )

    await message.answer(
        text,
        parse_mode="HTML",
    )


@router.message(Command("analytics"))
async def analytics(message: Message):

    data = await get_analytics()

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

    text = (
        f"📊 <b>Аналитика • {months[today.month]} {today.year}</b>\n\n"

        f"💰 Доходы: <b>{money(data['income'])}</b>\n"
        f"💸 Расходы: <b>{money(data['expense'])}</b>\n"
        f"🔁 Регулярные: <b>{money(data['recurring'])}/мес</b>\n"
        f"💎 Остаток: <b>{money(data['balance'])}</b>\n\n"

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

        for i, (name, amount) in enumerate(data["users"]):

            medal = medals[i] if i < len(medals) else "▪️"

            text += (
                f"{medal} {name} — <b>{money(amount)}</b>\n"
            )

    if data["categories"]:

        text += "\n🏆 <b>Категории</b>\n"

        for category, amount in data["categories"]:

            text += (
                f"📦 {category} — <b>{money(amount)}</b>\n"
            )

    if data["biggest"]:

        purchase = data["biggest"]

        purchase_date = purchase.created_at.strftime("%d.%m")

        text += (
            "\n🔥 <b>Крупнейшая покупка</b>\n"
            f"{purchase_date} • {purchase.title}\n"
            f"<b>{money(purchase.amount)}</b>"
        )

    await message.answer(
        text,
        parse_mode="HTML",
    )