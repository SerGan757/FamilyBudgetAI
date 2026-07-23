from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.services.statistics_service import (
    get_analytics,
    get_balance,
    get_month_statistics,
    get_today_statistics,
)

router = Router()


def money(value: float) -> str:
    return f"{value:,.2f} €".replace(",", " ")


def format_transaction(transaction):

    sign = "+" if transaction.type == "income" else "-"

    amount = f"{sign}{transaction.amount:.2f} €"

    if transaction.is_recurring:
        amount += "/мес"

    author = (
        transaction.user.name
        if getattr(transaction, "user", None)
        else ""
    )

    if transaction.is_recurring:

        return (
            f'{transaction.id:>4} '
            f'🔁 <b>{transaction.title}</b> '
            f'{amount} '
            f'{author}'
        )

    icon = "💰" if transaction.type == "income" else "💸"

    return (
        f'{transaction.id:>4} '
        f'{icon} '
        f'{transaction.title} '
        f'{amount} '
        f'{author}'
    )


def format_today(data):

    text = (
        f"📅 <b>{date.today().strftime('%d.%m.%Y')}</b>\n\n"
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

    regular = [
        t
        for t in data["transactions"]
        if not t.is_recurring
    ]

    if not regular:
        text += "Обычных операций нет."
    else:
        for transaction in regular:
            text += format_transaction(transaction) + "\n"

    return text


@router.message(Command("today"))
async def today(message: Message):

    data = await get_today_statistics()

    await message.answer(
        format_today(data),
        parse_mode="HTML",
    )


@router.message(Command("month"))
async def month(message: Message):

    data = await get_month_statistics()

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

    regular = [
        t
        for t in data["transactions"]
        if not t.is_recurring
    ]

    if not regular:
        text += "Обычных операций нет."
    else:
        for transaction in regular:
            text += format_transaction(transaction) + "\n"

    await message.answer(
        text,
        parse_mode="HTML",
    )


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