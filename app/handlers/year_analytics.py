import asyncio
from contextlib import suppress
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyKeyboardRemove

from app.i18n import all_texts, category_label, family_language, month_name, t
from app.keyboards.main_menu import main_menu_keyboard
from app.services.family_context_service import require_family_for_chat
from app.services.year_chart_service import (
    render_categories_chart,
    render_income_expense_chart,
    render_result_chart,
)
from app.services.year_analytics_service import get_year_analytics, get_year_category_transactions
from app.utils.currency import currency_symbol, family_currency, format_money

router = Router()


def _now_year(timezone_name):
    try: zone = ZoneInfo(timezone_name or "Europe/Berlin")
    except ZoneInfoNotFoundError: zone = ZoneInfo("Europe/Berlin")
    return datetime.now(zone).year


def _money(value, family, sign=False):
    prefix = "+" if sign and value > 0 else ""
    return prefix + format_money(value, family_currency(family))


def _category_display(language, label, custom_id):
    return label if custom_id is not None else category_label(language,label)


def _result_icon(value):
    return "🟢" if value > 0 else "🔴" if value < 0 else "⚪"


def year_keyboard(year, current_year, language):
    rows = [
        [InlineKeyboardButton(text=t(language,"year.months"),callback_data=f"year:months:{year}")],
        [InlineKeyboardButton(text=t(language,"year.categories"),callback_data=f"year:categories:{year}"), InlineKeyboardButton(text=t(language,"year.members"),callback_data=f"year:members:{year}")],
        [InlineKeyboardButton(text=t(language,"year.goals"),callback_data=f"year:goals:{year}")],
        [InlineKeyboardButton(text=t(language,"year.charts"),callback_data=f"year:charts:{year}")],
    ]
    years=[InlineKeyboardButton(text=f"⬅️ {year-1}",callback_data=f"year:main:{year-1}")]
    if year < current_year: years.append(InlineKeyboardButton(text=f"➡️ {year+1}",callback_data=f"year:main:{year+1}"))
    rows.extend([years,[InlineKeyboardButton(text=t(language,"nav.back"),callback_data="year:back:0")]])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def sub_keyboard(year, language):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(language,"year.back"),callback_data=f"year:main:{year}")]])


def chart_menu_keyboard(year, language):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📈 {t(language,'chart.income_expense')}",callback_data=f"yearchart:flow:{year}")],
        [InlineKeyboardButton(text=f"💎 {t(language,'chart.result')}",callback_data=f"yearchart:result:{year}")],
        [InlineKeyboardButton(text=f"🏆 {t(language,'chart.categories')}",callback_data=f"yearchart:categories:{year}")],
        [InlineKeyboardButton(text=t(language,"year.back"),callback_data=f"year:main:{year}")],
    ])


def chart_photo_keyboard(year, language):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language,"chart.back_charts"),callback_data=f"yearchartnav:menu:{year}")],
        [InlineKeyboardButton(text=t(language,"chart.back_year"),callback_data=f"yearchartnav:year:{year}")],
    ])


def _chart_title(language, key, year):
    return f"{t(language,key)} • {year}"


async def render_chart_menu(message, year, language):
    return await message.answer(
        f"📊 <b>{t(language,'chart.menu')} • {year}</b>",
        parse_mode="HTML", reply_markup=chart_menu_keyboard(year,language),
    )


async def _family(event):
    message = getattr(event,"message",None) or event
    return await require_family_for_chat(message.chat.id,chat_type=message.chat.type,telegram_id=event.from_user.id)


def _month_line(row, family, language):
    icon = _result_icon(row.result)
    return f"{month_name(language,row.month)}\n💰 {_money(row.income,family)} | 💸 {_money(row.expense,family)} | {icon} {_money(row.result,family,True)}"


async def render_year(message, family, year, edit=False):
    language=family_language(family); data=await get_year_analytics(family.id,year,family.timezone)
    if data.months:
        period=f"{month_name(language,data.months[0].month)} — {month_name(language,data.months[-1].month)} {year}"
    else: period=t(language,"year.no_data")
    lines=[f"📈 <b>{t(language,'year.title',year=year)}</b>","",f"📅 {t(language,'year.period')}: {period}",f"🗓 {t(language,'year.month_count')}: {data.months_with_data}","",f"💰 {t(language,'year.income')}: {_money(data.income,family)}",f"💸 {t(language,'year.expense')}: {_money(data.expense,family)}",f"🎯 {t(language,'year.to_goals')}: {_money(data.goal_contributions,family)}",f"{_result_icon(data.financial_result)} <b>{t(language,'year.result')}: {_money(data.financial_result,family,True)}</b>"]
    if data.months:
        lines += ["",f"📊 <b>{t(language,'year.average')}</b>",f"💰 {t(language,'year.income')}: {_money(data.average_income,family)}",f"💸 {t(language,'year.expense')}: {_money(data.average_expense,family)}",f"🎯 {t(language,'year.to_goals')}: {_money(data.average_goals,family)}","",f"🏆 <b>{t(language,'year.month_highlights')}</b>",f"💰 {t(language,'year.best_income')}: {month_name(language,data.best_income_month.month)} — {_money(data.best_income_month.income,family)}",f"💸 {t(language,'year.highest_expense')}: {month_name(language,data.highest_expense_month.month)} — {_money(data.highest_expense_month.expense,family)}",f"{_result_icon(data.best_result_month.result)} {t(language,'year.best_result')}: {month_name(language,data.best_result_month.month)} — {_money(data.best_result_month.result,family,True)}",f"{_result_icon(data.worst_result_month.result)} {t(language,'year.worst_result')}: {month_name(language,data.worst_result_month.month)} — {_money(data.worst_result_month.result,family,True)}","",f"📈 <b>{t(language,'year.dynamics')}</b>",*[_month_line(row,family,language) for row in data.months]]
    if data.categories: lines += ["",f"🏆 <b>{t(language,'year.categories')}</b>",*[f"{i}. {escape(_category_display(language,label,custom_id))} — {_money(amount,family)}" for i,(label,amount,custom_id) in enumerate(data.categories[:5],1)]]
    if data.members: lines += ["",f"👨‍👩‍👧 <b>{t(language,'year.members')}</b>",*[f"{i}. {escape(name)} — {_money(amount,family)}" for i,(name,amount) in enumerate(data.members,1)]]
    lines += ["",f"🔁 <b>{t(language,'year.recurring')}</b>",f"{t(language,'year.current_load')}:",f"💸 {_money(data.recurring_expense_load,family)}/{t(language,'common.monthly')}",f"💰 {_money(data.recurring_income_load,family)}/{t(language,'common.monthly')}",f"💸 {t(language,'year.actual_expense')}: {_money(data.recurring_actual_expense,family)}",f"💰 {t(language,'year.actual_income')}: {_money(data.recurring_actual_income,family)}"]
    if data.goals: lines += ["",f"🎯 <b>{t(language,'year.goals')}</b>",f"{t(language,'year.saved')}: {_money(data.goal_contributions,family)}",*[f"{name} — {_money(amount,family)}" for name,amount in data.goals[:3]]]
    inline_keyboard=year_keyboard(year,_now_year(family.timezone),language)
    if edit:
        return await message.edit_text("\n".join(lines),parse_mode="HTML",reply_markup=inline_keyboard)
    text="\n".join(lines)
    hide_message=await message.answer("…",reply_markup=ReplyKeyboardRemove())
    year_message=await message.answer(text,parse_mode="HTML",reply_markup=inline_keyboard)
    with suppress(Exception):
        await hide_message.delete()
    return year_message


@router.message(F.text.in_(all_texts("menu.year")))
async def year_menu(message:Message):
    family=await _family(message);await render_year(message,family,_now_year(family.timezone))


@router.callback_query(F.data.startswith("year:"))
async def year_callback(callback:CallbackQuery):
    if callback.message is None:return await callback.answer()
    family=await _family(callback);language=family_language(family)
    try: _,action,value=callback.data.split(":",2); year=int(value)
    except ValueError:return await callback.answer()
    if action=="back":
        await callback.message.delete()
        await callback.message.answer(t(language,"menu.title"),reply_markup=main_menu_keyboard(language))
        await callback.answer();return
    current=_now_year(family.timezone)
    if year>current: year=current
    if action=="main": await render_year(callback.message,family,year,True)
    elif action=="charts":
        await callback.message.edit_text(
            f"📊 <b>{t(language,'chart.menu')} • {year}</b>",
            parse_mode="HTML",reply_markup=chart_menu_keyboard(year,language),
        )
    else:
        data=await get_year_analytics(family.id,year,family.timezone)
        if action=="months": text=f"📊 <b>{t(language,'year.months')} • {year}</b>\n\n"+"\n\n".join(_month_line(row,family,language) for row in data.months)
        elif action=="members":
            text=f"👨‍👩‍👧 <b>{t(language,'year.members')} • {year}</b>\n\n"+"\n\n".join(f"{escape(name)}\n💸 {_money(amount,family)}\n📊 {round(amount/data.expense*100) if data.expense else 0}%" for name,amount in data.members)
        elif action=="goals": text=f"🎯 <b>{t(language,'year.goals')} • {year}</b>\n\n"+"\n".join(f"{escape(name)} — {_money(amount,family)}" for name,amount in data.goals)
        elif action=="categories":
            rows=[[InlineKeyboardButton(text=f"{_category_display(language,label,custom_id)} — {_money(amount,family)}",callback_data=f"yearcat:{year}:{index}")] for index,(label,amount,custom_id) in enumerate(data.categories)]
            rows.append([InlineKeyboardButton(text=t(language,"year.back"),callback_data=f"year:main:{year}")])
            await callback.message.edit_text(f"🏆 <b>{t(language,'year.categories')} • {year}</b>",parse_mode="HTML",reply_markup=InlineKeyboardMarkup(inline_keyboard=rows));await callback.answer();return
        else:return await callback.answer()
        await callback.message.edit_text(text or t(language,"year.no_data"),parse_mode="HTML",reply_markup=sub_keyboard(year,language))
    await callback.answer()


@router.callback_query(F.data.startswith("yearchart:"))
async def year_chart(callback:CallbackQuery):
    if callback.message is None:return await callback.answer()
    family=await _family(callback);language=family_language(family)
    try: _,kind,year_text=callback.data.split(":",2);year=int(year_text)
    except ValueError:return await callback.answer()
    year=min(year,_now_year(family.timezone))
    data=await get_year_analytics(family.id,year,family.timezone)
    months=tuple(month_name(language,index) for index in range(1,13))
    currency=currency_symbol(family_currency(family))
    if kind=="flow":
        key="chart.income_expense"
        png=await asyncio.to_thread(render_income_expense_chart,data,month_labels=months,title=_chart_title(language,key,year),income_label=t(language,"year.income"),expense_label=t(language,"year.expense"),currency=currency)
        filename=f"family_budget_{year}_income_expense.png"
    elif kind=="result":
        key="chart.result"
        png=await asyncio.to_thread(render_result_chart,data,month_labels=months,title=_chart_title(language,key,year),currency=currency)
        filename=f"family_budget_{year}_result.png"
    elif kind=="categories":
        key="chart.categories"
        categories=tuple((_category_display(language,label,custom_id),amount) for label,amount,custom_id in data.categories)
        png=await asyncio.to_thread(render_categories_chart,categories,title=_chart_title(language,key,year),currency=currency)
        filename=f"family_budget_{year}_categories.png"
    else:return await callback.answer()
    if not png:return await callback.answer(t(language,"chart.insufficient"),show_alert=True)
    await callback.message.answer_photo(
        BufferedInputFile(png,filename=filename),caption=f"<b>{_chart_title(language,key,year)}</b>",
        parse_mode="HTML",reply_markup=chart_photo_keyboard(year,language),
    )
    await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data.startswith("yearchartnav:"))
async def year_chart_navigation(callback:CallbackQuery):
    if callback.message is None:return await callback.answer()
    family=await _family(callback);language=family_language(family)
    try: _,target,year_text=callback.data.split(":",2);year=int(year_text)
    except ValueError:return await callback.answer()
    year=min(year,_now_year(family.timezone))
    await callback.message.delete()
    if target=="menu":await render_chart_menu(callback.message,year,language)
    elif target=="year":await render_year(callback.message,family,year)
    await callback.answer()


@router.callback_query(F.data.startswith("yearcat:"))
async def year_category(callback:CallbackQuery):
    family=await _family(callback);language=family_language(family)
    try: _,year_text,index_text=callback.data.split(":");year,index=int(year_text),int(index_text)
    except ValueError:return await callback.answer()
    data=await get_year_analytics(family.id,year,family.timezone)
    if index<0 or index>=len(data.categories):return await callback.answer(t(language,"category.not_found"),show_alert=True)
    label,amount,custom_id=data.categories[index]
    rows=await get_year_category_transactions(family.id,year,family.timezone,stored=label,custom_id=custom_id)
    text=f"<b>{escape(_category_display(language,label,custom_id))} • {year}</b>\n\n"+"\n".join(f"{tx.id} {escape(tx.title)} -{_money(tx.amount,family)} {escape(author)} {tx.created_at:%d.%m.%Y}" for tx,author in rows)+f"\n\n💸 {t(language,'category.total')}: {_money(amount,family)}"
    await callback.message.edit_text(text,parse_mode="HTML",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(language,"year.back"),callback_data=f"year:categories:{year}")]]));await callback.answer()
