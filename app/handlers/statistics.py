from datetime import date, timedelta
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyKeyboardRemove

from app.keyboards.pagination_keyboard import pagination_keyboard
from app.services.statistics_service import (
    get_analytics,
    get_balance,
    get_month_statistics,
    get_today_statistics,
)
from app.services.analytics_forecast import calculate_analytics_forecast
from app.services.family_context_service import require_family_for_chat
from app.utils.navigation import answer_with_navigation
from app.utils.transaction_format import project_suffix
from app.utils.temporary_screens import refresh_temporary_message, schedule_temporary_message
from app.utils.currency import family_currency, format_money
from app.i18n import category_label, family_language, month_name, t
from app.services.savings_goal_service import progress_bar
from app.keyboards.categories import CategoryCallback

router = Router()

LIMIT = 20


def days_text(value: int, language: str = "ru") -> str:
    if language == "en":
        return f"{value} day" if value == 1 else f"{value} days"
    if language == "de":
        return f"{value} Tag" if value == 1 else f"{value} Tage"
    if language == "pl":
        word = "dzień" if value == 1 else ("dni" if value % 10 in (2, 3, 4) and value % 100 not in (12, 13, 14) else "dni")
        return f"{value} {word}"
    if language == "cs":
        return f"{value} " + ("den" if value == 1 else "dny" if value in (2, 3, 4) else "dní")
    if language == "sk":
        return f"{value} " + ("deň" if value == 1 else "dni" if value in (2, 3, 4) else "dní")
    if language == "ro":
        return f"{value} " + ("zi" if value == 1 else "zile")
    if language == "bg":
        return f"{value} " + ("ден" if value == 1 else "дни")
    if language == "hu":
        return f"{value} nap"
    if language == "uk":
        word = "день" if value % 10 == 1 and value % 100 != 11 else ("дні" if value % 10 in (2, 3, 4) and value % 100 not in (12, 13, 14) else "днів")
        return f"{value} {word}"
    if language == "be":
        word = "дзень" if value % 10 == 1 and value % 100 != 11 else ("дні" if value % 10 in (2, 3, 4) and value % 100 not in (12, 13, 14) else "дзён")
        return f"{value} {word}"
    if value % 10 == 1 and value % 100 != 11:
        word = "день"
    elif value % 10 in (2, 3, 4) and value % 100 not in (12, 13, 14):
        word = "дня"
    else:
        word = "дней"
    return f"{value} {word}"


def money(value: float, currency_code: str = "EUR") -> str:
    return format_money(value, currency_code)


def format_transaction(transaction, currency_code: str = "EUR", language: str = "ru"):

    if getattr(transaction, "kind", "transaction") == "goal_contribution":
        author = escape(transaction.user_name)[:3] if transaction.user_name else ""
        return (
            f"{transaction.id} 🎯 {escape(transaction.title)} "
            f"+{money(transaction.amount, currency_code)} {author}"
        )

    sign = "+" if transaction.type == "income" else "-"

    amount = abs(transaction.amount)

    amount_text = f"{sign}{money(amount, currency_code)}"

    if transaction.is_recurring:
        amount_text += f"/{t(language, 'common.monthly')}"

    localized_category = category_label(language, transaction.category)
    base_icon = "💰" if transaction.type == "income" else escape(localized_category.split()[0])
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
        f"{(' 📁 ' + escape(transaction.project_name)) if getattr(transaction, 'project_name', None) else project_suffix(transaction)}"
    )


def format_today(
    data,
    selected_date: date,
    offset: int = 0,
    currency_code: str = "EUR",
    language: str = "ru",
):

    text = (
        f"📅 <b>{selected_date.strftime('%d.%m.%Y')}</b>\n\n"
        f"💰 {t(language, 'common.income')}     {money(data['income'], currency_code)}\n"
        f"💸 {t(language, 'common.expense')}    {money(data['expense'], currency_code)}\n"
        f"📈 {t(language, 'common.balance')}     {money(data['balance'], currency_code)}\n"
        f"🎯 {t(language, 'goal.to_goal')}     {money(data.get('goal_contributions', 0), currency_code)}\n"
        f"💶 {t(language, 'goal.free_balance')}     {money(data['balance'] - data.get('goal_contributions', 0), currency_code)}\n"
    )

    text += "\n"

    regular = data["transactions"]

    total = data["total"]
    if not regular:

        text += t(language, "common.none")

    else:

        for transaction in regular:

            text += (
                format_transaction(transaction, currency_code, language)
                + "\n"
            )

    shown = min(
        offset + LIMIT,
        total,
    )

    text += (
        f"\n<b>{t(language, 'common.shown', shown=shown, total=total)}</b>"
    )

    return text


@router.message(Command("today"))
async def today(message: Message):
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type,
        telegram_id=message.from_user.id,
    )

    selected_date = date.today()
    data = await get_today_statistics(
        family.id,
        selected_date=selected_date,
        offset=0,
        limit=LIMIT,
    )

    total = data["total"]

    sent_message = await answer_with_navigation(
        message,
        format_today(
            data,
            selected_date,
            offset=0,
            currency_code=family_currency(family),
            language=family_language(family),
        ),
        parse_mode="HTML",
        inline_markup=day_keyboard(selected_date, 0, total, family_language(family)),
    )
    schedule_temporary_message(sent_message, ttl=family.temporary_screen_ttl)


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

    family = await require_family_for_chat(
        callback.message.chat.id, chat_type=callback.message.chat.type,
        telegram_id=callback.from_user.id,
    )

    data = await get_today_statistics(
        family.id,
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
            currency_code=family_currency(family),
            language=family_language(family),
        ),
        parse_mode="HTML",
        reply_markup=day_keyboard(selected_date, offset, total, family_language(family)),
    )
    refresh_temporary_message(callback.message, ttl=family.temporary_screen_ttl)
    await callback.answer()


def format_month(
    data,
    year: int,
    month: int,
    offset: int = 0,
    currency_code: str = "EUR",
    language: str = "ru",
):
    text = (
        f"📅 <b>{month_name(language, month)} {year}</b>\n\n"
        f"💰 {t(language, 'common.income')}: {money(data['ordinary_income'], currency_code)}\n"
        f"💸 {t(language, 'common.expense')}: {money(data['ordinary_expense'], currency_code)}\n\n"
        f"🔁 {t(language, 'balance.reg_expense')}: {money(data['recurring_expense'], currency_code)}/{t(language, 'common.monthly')} ({data['recurring_expense_count']})\n"
        f"🔁 {t(language, 'balance.reg_income')}: {money(data['recurring_income'], currency_code)}/{t(language, 'common.monthly')} ({data['recurring_income_count']})\n\n"
        f"📈 {t(language, 'common.balance')}: {money(data['balance'], currency_code)}\n"
        f"🎯 {t(language, 'goal.to_goal')}: {money(data.get('goal_contributions', 0), currency_code)}\n"
        f"💶 {t(language, 'goal.free_balance')}: {money(data['balance'] - data.get('goal_contributions', 0), currency_code)}\n\n"
    )

    regular = data["transactions"]

    total = data["total"]

    if not regular:

        text += t(language, "month.empty")

    else:

        for transaction in regular:

            text += (
                format_transaction(transaction, currency_code, language)
                + "\n"
            )

    shown = min(
        offset + LIMIT,
        total,
    )

    text += (
        f"\n<b>{t(language, 'common.shown', shown=shown, total=total)}</b>"
    )

    return text


def day_keyboard(selected_date: date, offset: int, total: int, language: str = "ru") -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(text=t(language, "nav.prev_day"), callback_data=f"day:{(selected_date - timedelta(days=1)).isoformat()}"),
        InlineKeyboardButton(text=t(language, "nav.next_day"), callback_data=f"day:{(selected_date + timedelta(days=1)).isoformat()}"),
    ]]
    page = []
    if offset > 0:
        page.append(InlineKeyboardButton(text=t(language, "nav.prev_20"), callback_data=f"today:{selected_date.isoformat()}:page:{max(0, offset-LIMIT)}"))
    if offset + LIMIT < total:
        page.append(InlineKeyboardButton(text=t(language, "nav.next_20"), callback_data=f"today:{selected_date.isoformat()}:page:{offset+LIMIT}"))
    if page:
        rows.append(page)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + month - 1 + delta
    return index // 12, index % 12 + 1


def month_keyboard(year: int, month: int, offset: int, total: int, language: str = "ru") -> InlineKeyboardMarkup:
    previous_year, previous_month = _shift_month(year, month, -1)
    next_year, next_month = _shift_month(year, month, 1)
    rows = [[
        InlineKeyboardButton(text=t(language, "nav.prev_month"), callback_data=f"month:{previous_year}:{previous_month:02d}"),
        InlineKeyboardButton(text=t(language, "nav.next_month"), callback_data=f"month:{next_year}:{next_month:02d}"),
    ]]
    page = []
    if offset > 0:
        page.append(InlineKeyboardButton(text=t(language, "nav.prev_20"), callback_data=f"month:{year}:{month:02d}:{max(0, offset-LIMIT)}"))
    if offset + LIMIT < total:
        page.append(InlineKeyboardButton(text=t(language, "nav.next_20"), callback_data=f"month:{year}:{month:02d}:{offset+LIMIT}"))
    if page:
        rows.append(page)
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("month"))
async def month(message: Message):
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type,
        telegram_id=message.from_user.id,
    )

    today = date.today()
    data = await get_month_statistics(
        family.id,
        year=today.year,
        month=today.month,
        offset=0,
        limit=LIMIT,
    )

    total = data["total"]
   

    sent_message = await answer_with_navigation(
        message,
        format_month(
            data,
            today.year,
            today.month,
            offset=0,
            currency_code=family_currency(family),
            language=family_language(family),
        ),
        parse_mode="HTML",
        inline_markup=month_keyboard(today.year, today.month, 0, total, family_language(family)),
    )
    schedule_temporary_message(sent_message, ttl=family.temporary_screen_ttl)
    return


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

    family = await require_family_for_chat(
        callback.message.chat.id, chat_type=callback.message.chat.type,
        telegram_id=callback.from_user.id,
    )

    data = await get_month_statistics(
        family.id,
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
            currency_code=family_currency(family),
            language=family_language(family),
        ),
        parse_mode="HTML",
        reply_markup=month_keyboard(year, month, offset, total, family_language(family)),
    )
    refresh_temporary_message(callback.message, ttl=family.temporary_screen_ttl)
    await callback.answer()


@router.message(Command("balance"))
async def balance(message: Message):
    family = await require_family_for_chat(
        message.chat.id, chat_type=message.chat.type,
        telegram_id=message.from_user.id,
    )
    data = await get_balance(family.id)
    language = family_language(family)

    text = (
        f"<b>{t(language, 'balance.title')}</b>\n\n"
        f"💰 {t(language, 'common.income')}: {money(data['ordinary_income'], family_currency(family))}\n"
        f"💸 {t(language, 'common.expense')}: {money(data['ordinary_expense'], family_currency(family))}\n\n"
        f"🔁 {t(language, 'balance.reg_expense')}: {money(data['recurring_expense'], family_currency(family))}/{t(language, 'common.monthly')} ({data['recurring_expense_count']})\n"
        f"🔁 {t(language, 'balance.reg_income')}: {money(data['recurring_income'], family_currency(family))}/{t(language, 'common.monthly')} ({data['recurring_income_count']})\n\n"
        f"🎯 {t(language, 'goal.reserved')}: {money(data.get('goal_contributions', 0), family_currency(family))}\n"
        f"💶 {t(language, 'goal.free_balance')}: {money(data.get('free_balance', data['balance']), family_currency(family))}\n\n"
        f"<b>💎 {t(language, 'balance.remaining')}: {money(data['balance'], family_currency(family))}</b>"
    )

    sent_message = await message.answer(
        text,
        parse_mode="HTML",
    )
    schedule_temporary_message(sent_message, ttl=family.temporary_screen_ttl)


@router.message(Command("analytics"))
async def analytics(
    message: Message,
    year: int | None = None,
    month: int | None = None,
    family_id: int | None = None,
    *,
    edit_existing: bool = False,
    temporary_screen_ttl: int = 20,
    currency_code: str = "EUR",
    language: str = "ru",
):
    if family_id is None:
        family = await require_family_for_chat(
            message.chat.id, chat_type=message.chat.type,
            telegram_id=message.from_user.id,
        )
        family_id = family.id
        temporary_screen_ttl = family.temporary_screen_ttl
        currency_code = family_currency(family)
        language = family_language(family)

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
    data = await get_analytics(family_id, year, month, include_goal=True)
    goal_snapshot = data.get("goal")
    total_income = data["ordinary_income"] + data["recurring_income"]
    forecast = calculate_analytics_forecast(
        year, month, total_income,
        data["ordinary_expense"], data["recurring_expense"],
    )

    forecast_lines = [
        f"📅 {t(language, 'analytics.days_left', days=days_text(forecast.days_remaining, language), percent=forecast.elapsed_percent)}",
    ]
    if forecast.spent_percent is not None:
        forecast_lines.append(f"💸 {t(language, 'analytics.spent', percent=forecast.spent_percent)}")
    if forecast.forecast_expenses is not None:
        forecast_lines.append(
            f"📈 {t(language, 'analytics.forecast_expense')}: {money(forecast.forecast_expenses, currency_code)}"
        )
    if forecast.forecast_balance is not None:
        if forecast.forecast_balance >= 0:
            forecast_lines.append(
                f"🟢 {t(language, 'analytics.forecast_remaining')}: {money(forecast.forecast_balance, currency_code)}"
            )
        else:
            forecast_lines.append(
                f"🔴 {t(language, 'analytics.forecast_deficit')}: {money(abs(forecast.forecast_balance), currency_code)}"
            )
    if forecast.pace_delta is not None:
        if forecast.pace_delta > 2:
            pace = f"⚠️ {t(language, 'analytics.pace_high', percent=forecast.pace_delta)}"
        elif forecast.pace_delta < -2:
            pace = f"✅ {t(language, 'analytics.pace_low', percent=abs(forecast.pace_delta))}"
        else:
            pace = f"✅ {t(language, 'analytics.pace_ok')}"
        forecast_lines.append(pace)
    forecast_text = "\n".join(forecast_lines)

    text = (
        f"📊 <b>{t(language, 'analytics.title')} • {month_name(language, month)} {year}</b>\n\n"

        f"💰 {t(language, 'analytics.ordinary_income')}: <b>{money(data['ordinary_income'], currency_code)}</b>\n"
        f"💸 {t(language, 'analytics.ordinary_expense')}: <b>{money(data['ordinary_expense'], currency_code)}</b>\n\n"
        f"🔁 {t(language, 'analytics.reg_income')}: <b>{money(data['recurring_income'], currency_code)}/{t(language, 'common.monthly')} ({data['recurring_income_count']})</b>\n"
        f"🔁 {t(language, 'analytics.reg_expense')}: <b>{money(data['recurring_expense'], currency_code)}/{t(language, 'common.monthly')} ({data['recurring_expense_count']})</b>\n\n"
        f"💎 {t(language, 'analytics.month_balance')}: <b>{money(data['balance'], currency_code)}</b>\n\n"
        f"{forecast_text}\n\n"

        f"📋 {t(language, 'common.operations')}: <b>{data['operations']}</b>\n"
        f"🧾 {t(language, 'analytics.average')}: <b>{money(data['average_check'], currency_code)}</b>\n"
        f"📅 {t(language, 'analytics.per_day')}: <b>{money(data['average_day'], currency_code)}</b>\n"
    )
    if data["users"]:

        text += f"\n👨 <b>{t(language, 'analytics.members')}</b>\n"

        medals = [
            "🥇",
            "🥈",
            "🥉",
        ]

        for i, (name, amount) in enumerate(data["users"][:5]):

            medal = medals[i] if i < len(medals) else "▪️"

            text += (
                f"{medal} {escape(name)} — <b>{money(amount, currency_code)}</b>\n"
            )

    if data["categories"]:

        text += f"\n🏆 <b>{t(language, 'analytics.categories')}</b>\n"

        for i, (category, amount) in enumerate(data["categories"][:5], 1):

            text += (
                f"{i}. {escape(category_label(language, category))} — <b>{money(amount, currency_code)}</b>\n"
            )

    if data["biggest"]:

        purchase = data["biggest"]

        purchase_date = purchase.created_at.strftime("%d.%m")

        text += (
            f"\n🔥 <b>{t(language, 'analytics.biggest')}</b>\n"
            f"{purchase_date} • {escape(purchase.title)}\n"
            f"<b>{money(purchase.amount, currency_code)}</b>"
        )

    if data["projects"]:
        text += f"\n\n📁 <b>{t(language, 'analytics.projects')}</b>\n"
        for index, (project_name, amount) in enumerate(data["projects"], 1):
            text += (
                f"{index}. {escape(project_name)} — <b>{money(amount, currency_code)}</b>\n"
            )

    if goal_snapshot is not None:
        goal = goal_snapshot.goal
        free_balance = data["balance"] - goal_snapshot.month_contributions
        text += (
            f"\n\n🎯 <b>{t(language, 'goal.title')}: {escape(goal.name)}</b>\n\n"
            f"🏦 {t(language, 'goal.saved')}: {money(goal_snapshot.saved, currency_code)} / {money(goal.target_amount, currency_code)}\n"
            f"{progress_bar(goal_snapshot.saved, goal.target_amount)}\n"
        )
        if goal_snapshot.remaining > 0:
            text += f"💰 {t(language, 'goal.remaining')}: {money(goal_snapshot.remaining, currency_code)}\n"
        else:
            text += f"🎉 {t(language, 'goal.reached')}\n"
        text += (
            f"📥 {t(language, 'goal.month')}: +{money(goal_snapshot.month_contributions, currency_code)}\n"
            f"💶 {t(language, 'goal.free_balance')}: {money(free_balance, currency_code)}\n"
        )
        if goal_snapshot.days_to_goal is None:
            text += f"📈 {t(language, 'goal.no_forecast')}\n"
        else:
            text += f"⏳ {t(language, 'goal.current_pace', days=goal_snapshot.days_to_goal)}\n"
            if goal_snapshot.expected_date:
                text += (
                    f"📅 {t(language, 'goal.expected')}: "
                    f"{month_name(language, goal_snapshot.expected_date.month)} {goal_snapshot.expected_date.year}\n"
                )
        if goal.deadline and goal_snapshot.required_per_month is not None:
            text += f"📌 {t(language, 'goal.required_month')}: {money(goal_snapshot.required_per_month, currency_code)}/{t(language, 'common.monthly')}\n"
            if goal_snapshot.current_per_month is not None:
                text += f"📈 {t(language, 'goal.current_month')}: ~{money(goal_snapshot.current_per_month, currency_code)}/{t(language, 'common.monthly')}\n"
                difference = abs(goal_snapshot.pace_difference or 0)
                if (goal_snapshot.pace_difference or 0) < 0:
                    text += f"⚠️ {t(language, 'goal.pace_short')}: {money(difference, currency_code)}/{t(language, 'common.monthly')}\n"
                else:
                    text += f"✅ {t(language, 'goal.pace_ahead')}: {money(difference, currency_code)}/{t(language, 'common.monthly')}\n"
            if goal_snapshot.schedule_months is not None:
                if goal_snapshot.schedule_months > 0:
                    text += f"🕒 {t(language, 'goal.delay')}: ~{goal_snapshot.schedule_months} {t(language, 'common.monthly')}\n"
                elif goal_snapshot.schedule_months < 0:
                    text += f"🚀 {t(language, 'goal.ahead')}: ~{abs(goal_snapshot.schedule_months)} {t(language, 'common.monthly')}\n"
                else:
                    text += f"✅ {t(language, 'goal.on_schedule')}\n"

    if edit_existing:
        await message.edit_text(
            text, parse_mode="HTML", reply_markup=analytics_keyboard(year, month, language),
        )
    else:
        sent_message = await answer_with_navigation(
            message, text, parse_mode="HTML",
            inline_markup=analytics_keyboard(year, month, language),
        )
        schedule_temporary_message(sent_message, ttl=temporary_screen_ttl)


def analytics_keyboard(year: int, month: int, language: str = "ru") -> InlineKeyboardMarkup:
    previous_year, previous_month = _shift_month(year, month, -1)
    next_year, next_month = _shift_month(year, month, 1)
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(language, "nav.prev_month"), callback_data=f"analytics:{previous_year}:{previous_month:02d}"),
            InlineKeyboardButton(text=t(language, "nav.next_month"), callback_data=f"analytics:{next_year}:{next_month:02d}"),
        ],
        [InlineKeyboardButton(
            text=t(language, "analytics.help_button"),
            callback_data=f"analytics_help:{year}:{month:02d}",
        )],
        [InlineKeyboardButton(
            text=f"🏷 {t(language, 'analytics.categories')}",
            callback_data=CategoryCallback(
                action="list", value=f"analytics-{year:04d}-{month:02d}",
            ).pack(),
        )],
    ])


def analytics_help_keyboard(year: int, month: int, language: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=t(language, "analytics.back"),
        callback_data=f"analytics_back:{year}:{month:02d}",
    )]])


ANALYTICS_HELP_TEXT = """📊 <b>Как читать прогноз</b>

📅 До конца месяца — сколько дней осталось. Процент в скобках показывает, какая часть месяца уже прошла.

💸 Потрачено бюджета — какая часть ожидаемых доходов месяца уже приходится на расходы.

📈 Прогноз расходов — примерные общие расходы к концу месяца, если текущий темп обычных расходов сохранится.

🟢 Прогноз остатка — сколько денег предположительно останется к концу месяца.

🔴 Прогноз дефицита — сколько денег предположительно не хватит к концу месяца.

⚠️ Превышение темпа расходов — насколько расходы идут быстрее равномерного расходования бюджета в течение месяца.

Прогноз автоматически меняется после новых операций."""


@router.callback_query(F.data.startswith("analytics_help:"))
async def analytics_help(callback: CallbackQuery):
    try:
        _, year, month = callback.data.split(":")
        year, month = int(year), int(month)
        if not 1 <= month <= 12:
            raise ValueError
    except ValueError:
        await callback.answer("Некорректный месяц", show_alert=True)
        return
    family = await require_family_for_chat(
        callback.message.chat.id, chat_type=callback.message.chat.type,
        telegram_id=callback.from_user.id,
    )
    await callback.message.edit_text(
        f"📊 <b>{t(family_language(family), 'analytics.help_title').removeprefix('📊 ')}</b>\n\n{t(family_language(family), 'analytics.help')}",
        parse_mode="HTML",
        reply_markup=analytics_help_keyboard(year, month, family_language(family)),
    )
    refresh_temporary_message(callback.message, ttl=family.temporary_screen_ttl)
    await callback.answer()


@router.callback_query(F.data.startswith("analytics_back:"))
async def analytics_back(callback: CallbackQuery):
    try:
        _, year, month = callback.data.split(":")
        year, month = int(year), int(month)
        if not 1 <= month <= 12:
            raise ValueError
    except ValueError:
        await callback.answer("Некорректный месяц", show_alert=True)
        return
    family = await require_family_for_chat(
        callback.message.chat.id, chat_type=callback.message.chat.type,
        telegram_id=callback.from_user.id,
    )
    await analytics(
        callback.message, year, month, family.id,
        edit_existing=True, currency_code=family_currency(family), language=family_language(family),
    )
    refresh_temporary_message(callback.message, ttl=family.temporary_screen_ttl)
    await callback.answer()


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
    family = await require_family_for_chat(
        callback.message.chat.id, chat_type=callback.message.chat.type,
        telegram_id=callback.from_user.id,
    )
    try:
        await analytics(
            callback.message, year, month, family.id,
            edit_existing=True, currency_code=family_currency(family), language=family_language(family),
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).lower():
            raise
        refresh_temporary_message(callback.message, ttl=family.temporary_screen_ttl)
    else:
        refresh_temporary_message(callback.message, ttl=family.temporary_screen_ttl)
    finally:
        await callback.answer()
