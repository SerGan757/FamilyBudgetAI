from datetime import date, datetime
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.data.categories import CATEGORIES
from app.handlers.category_states import CategorySettingsState
from app.i18n import category_label, family_language, month_name, t
from app.keyboards.categories import (
    CategoryCallback, cancel_add_keyboard, categories_keyboard,
    category_card_keyboard, keyword_pages_keyboard, operations_keyboard,
    custom_archive_keyboard, custom_card_keyboard, custom_input_cancel_keyboard,
    custom_create_cancel_keyboard, custom_manual_icon_cancel_keyboard, icon_keyboard,
)
from app.services.category_override_service import (
    EDITABLE_CATEGORY_KEYS, SETTINGS_CATEGORY_KEYS, add_family_keywords,
    disable_family_keyword, get_disabled_keywords, get_effective_category_catalog,
    get_effective_keywords, normalize_keyword, restore_family_keyword,
    stored_category_for_key,
)
from app.services.family_context_service import require_family_for_chat
from app.services.history_service import get_transactions_by_category_page
from app.services.custom_category_service import (
    add_custom_keywords, create_custom_category, delete_custom_category,
    get_custom_category, list_custom_categories, remove_custom_keyword,
    set_custom_category_active, update_custom_category,
)
from app.utils.currency import family_currency, format_money
from app.utils.temporary_screens import refresh_temporary_message


router = Router()
KEYWORDS_PER_PAGE = 15


def _category_title(key: str, language: str) -> str:
    return category_label(language, stored_category_for_key(key) or "")


def _item_value(item, index: int, attribute: str):
    return item[index] if isinstance(item, tuple) else getattr(item, attribute, None)


async def keyword_result_summary(family, items, *, include_restored: bool):
    """Build one transparent summary for system and custom keyword mutations."""
    language = family_language(family)
    counts = {status: 0 for status in ("added", "restored", "already_exists", "conflict")}
    conflicts = []
    existing = []
    for item in items:
        keyword = _item_value(item, 0, "keyword")
        status = _item_value(item, 1, "status")
        conflict_ref = _item_value(item, 2, "conflict_category_key")
        if status in counts:
            counts[status] += 1
        if status == "already_exists":
            existing.append(keyword)
        if status == "conflict":
            label = ""
            if conflict_ref and str(conflict_ref).startswith("system:"):
                label = _category_title(str(conflict_ref).split(":", 1)[1], language)
            elif conflict_ref and str(conflict_ref).startswith("custom:"):
                try:
                    category_id = int(str(conflict_ref).split(":", 1)[1])
                except ValueError:
                    category_id = 0
                category = await get_custom_category(family.id, category_id)
                if category is not None:
                    label = f"{category.icon} {category.name}"
            elif conflict_ref:
                label = _category_title(str(conflict_ref), language)
            conflicts.append((keyword, label or t(language, "category.not_found")))
    lines = [f"✅ {t(language, 'category.bulk_added')}: {counts['added']}"]
    if include_restored:
        lines.append(f"♻️ {t(language, 'category.bulk_restored')}: {counts['restored']}")
    lines.extend([
        f"ℹ️ {t(language, 'category.bulk_existing')}: {counts['already_exists']}",
        f"⚠️ {t(language, 'category.bulk_conflicting')}: {counts['conflict']}",
    ])
    if existing and len(existing) <= 5:
        lines.extend(["", *(f"• {escape(keyword)}" for keyword in existing)])
    if conflicts:
        lines.extend(["", f"⚠️ <b>{t(language, 'category.bulk_conflicts')}:</b>"])
        lines.extend(
            f"• {escape(keyword)} → {escape(label)}" for keyword, label in conflicts
        )
    return lines


async def _family(callback_or_message):
    message = getattr(callback_or_message, "message", None) or callback_or_message
    return await require_family_for_chat(
        message.chat.id,
        chat_type=message.chat.type,
        telegram_id=callback_or_message.from_user.id,
    )


async def show_category_list(message, family, origin="settings"):
    language = family_language(family)
    catalog = await get_effective_category_catalog(family.id)
    custom = await list_custom_categories(family.id, True)
    archived = await list_custom_categories(family.id, False)
    await message.edit_text(
        f"🏷 <b>{t(language, 'category.title')}</b>",
        reply_markup=categories_keyboard(catalog, language, origin=origin, custom=custom, archived=archived),
        parse_mode="HTML",
    )


async def show_category_card(message, family, key: str, page=0, origin="settings"):
    if key not in SETTINGS_CATEGORY_KEYS:
        return False
    language = family_language(family)
    entries = await get_effective_keywords(family.id, key)
    page = max(0, min(page, max(0, (len(entries) - 1) // KEYWORDS_PER_PAGE)))
    start = page * KEYWORDS_PER_PAGE
    visible = entries[start:start + KEYWORDS_PER_PAGE]
    lines = [
        f"<b>{escape(_category_title(key, language))}</b>",
        "",
        f"🔑 {t(language, 'category.keyword_count', count=len(entries))}",
    ]
    if key == "other":
        lines.extend(["", t(language, "category.fallback")])
    elif visible:
        lines.append("")
        lines.extend(
            f"{'➕ ' if entry.source == 'family' else ''}{escape(entry.keyword)}"
            for entry in visible
        )
    else:
        lines.extend(["", t(language, "category.no_keywords")])
    await message.edit_text(
        "\n".join(lines),
        reply_markup=category_card_keyboard(
            key, language, page, origin=origin, total=len(entries),
        ),
        parse_mode="HTML",
    )
    return True


async def show_custom_category_card(message, family, category_id: int, origin="settings"):
    category = await get_custom_category(family.id, category_id)
    if category is None:
        return False
    language = family_language(family)
    text = custom_category_card_text(category, language)
    await message.edit_text(
        text, parse_mode="HTML",
        reply_markup=custom_card_keyboard(
            category.id, language, origin, archived=not category.is_active,
        ),
    )
    return True


def custom_category_card_text(category, language: str, notice: str | None = None):
    lines = [
        f"<b>{escape(category.icon)} {escape(category.name)}</b>",
        "",
        f"🔑 {t(language, 'category.keyword_count', count=len(category.keywords))}",
    ]
    if category.keywords:
        lines.extend(["", *(escape(keyword.keyword) for keyword in category.keywords[:15])])
    if notice:
        lines = [notice, "", *lines]
    return "\n".join(lines)


async def answer_custom_category_card(message, family, category_id: int, origin="settings", notice=None):
    category = await get_custom_category(family.id, category_id)
    if category is None:
        return False
    language = family_language(family)
    await message.answer(
        custom_category_card_text(category, language, notice), parse_mode="HTML",
        reply_markup=custom_card_keyboard(
            category.id, language, origin, archived=not category.is_active,
        ),
    )
    return True


def _period(value: str):
    if value == "all":
        return None, None, True
    year, month = map(int, value.split("-"))
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end, False


async def show_category_operations(message, family, key: str, value: str):
    if key not in SETTINGS_CATEGORY_KEYS:
        return False
    try:
        origin, period, offset_text = value.split("|")
        offset = max(0, int(offset_text))
        if period == "current":
            today = date.today()
            period = f"{today.year:04d}-{today.month:02d}"
        start, end, all_time = _period(period)
    except (ValueError, TypeError):
        return False
    stored = stored_category_for_key(key)
    transactions, total, amount = await get_transactions_by_category_page(
        family.id, stored, 20, offset, start, end,
    )
    language = family_language(family)
    heading = (
        t(language, "category.all_time")
        if all_time else f"{month_name(language, start.month)} {start.year}"
    )
    lines = [f"<b>{escape(_category_title(key, language))} • {escape(heading)}</b>", ""]
    if transactions:
        for transaction in transactions:
            lines.append(
                f"{transaction.id} {escape(transaction.title)} "
                f"-{format_money(transaction.amount, family_currency(family))} "
                f"{escape(getattr(transaction, 'user_name', ''))} "
                f"{transaction.created_at:%d.%m.%Y}"
            )
    else:
        lines.append(t(language, "category.no_operations"))
    lines.extend([
        "",
        f"💸 {t(language, 'category.total')}: {format_money(amount, family_currency(family))}",
        f"🧾 {t(language, 'common.operations')}: {total}",
    ])
    await message.edit_text(
        "\n".join(lines), parse_mode="HTML",
        reply_markup=operations_keyboard(
            key, start.year if start else date.today().year,
            start.month if start else date.today().month,
            offset, total, language, origin, all_time,
        ),
    )
    return True


@router.message(F.text == "🏷 Категории")
async def categories_from_legacy_settings(message: Message):
    family = await _family(message)
    catalog = await get_effective_category_catalog(family.id)
    custom = await list_custom_categories(family.id, True)
    archived = await list_custom_categories(family.id, False)
    await message.answer(
        f"🏷 <b>{t(family_language(family), 'category.title')}</b>",
        reply_markup=categories_keyboard(
            catalog, family_language(family), custom=custom, archived=archived,
        ),
        parse_mode="HTML",
    )


@router.callback_query(CategoryCallback.filter())
async def category_callback(callback: CallbackQuery, callback_data: CategoryCallback, state: FSMContext):
    message = callback.message
    if message is None:
        await callback.answer()
        return
    family = await _family(callback)
    language = family_language(family)
    action, key, value = callback_data.action, callback_data.key, callback_data.value
    if action not in {
        "add", "custom_icon", "custom_other_icon", "custom_icon_picker",
        "custom_create_cancel",
    }:
        await state.clear()
    if action == "list":
        await show_category_list(message, family, value or "settings")
    elif action == "card":
        parts = (value or "settings").split("|")
        origin = parts[0]
        try:
            page = int(parts[1]) if len(parts) > 1 else 0
        except ValueError:
            await callback.answer(t(language, "category.not_found"), show_alert=True)
            return
        if not await show_category_card(message, family, key, page, origin):
            await callback.answer(t(language, "category.not_found"), show_alert=True)
            return
    elif action == "add" and key in EDITABLE_CATEGORY_KEYS:
        await state.set_state(CategorySettingsState.waiting_for_keyword)
        await state.update_data(category_key=key, category_origin=value or "settings", family_id=family.id)
        await message.edit_text(
            (
                f"<b>{t(language, 'category.bulk_title')}</b>\n\n"
                f"{t(language, 'category.bulk_prompt')}\n\n"
                f"{t(language, 'category.bulk_example')}\n\n"
                f"{t(language, 'category.bulk_max')}"
            ),
            reply_markup=cancel_add_keyboard(key, language, value or "settings"),
            parse_mode="HTML",
        )
    elif action in {"disable", "disabled"} and key in EDITABLE_CATEGORY_KEYS:
        parts = (value or "settings|0").split("|")
        origin = parts[0]
        try:
            page = int(parts[1]) if len(parts) > 1 else 0
        except ValueError:
            await callback.answer(t(language, "category.not_found"), show_alert=True)
            return
        entries = (
            await get_effective_keywords(family.id, key)
            if action == "disable" else await get_disabled_keywords(family.id, key)
        )
        await message.edit_text(
            t(language, "category.choose_disable" if action == "disable" else "category.disabled_title"),
            reply_markup=keyword_pages_keyboard(action, key, entries, page, language, origin),
        )
    elif action in {"disable_one", "disabled_one"} and key in EDITABLE_CATEGORY_KEYS:
        try:
            origin, page_text, index_text = value.split("|")
            page, index = int(page_text), int(index_text)
            entries = (
                await get_effective_keywords(family.id, key)
                if action == "disable_one" else await get_disabled_keywords(family.id, key)
            )
            entry = entries[index]
        except (ValueError, IndexError):
            await callback.answer(t(language, "category.not_found"), show_alert=True)
            return
        if action == "disable_one":
            await disable_family_keyword(family.id, key, entry.normalized_keyword)
        else:
            await restore_family_keyword(family.id, key, entry.normalized_keyword)
        await show_category_card(message, family, key, page, origin)
    elif action == "ops":
        if not await show_category_operations(message, family, key, value):
            await callback.answer(t(language, "category.not_found"), show_alert=True)
            return
    elif action == "custom_new":
        await state.set_state(CategorySettingsState.waiting_for_custom_name)
        await state.update_data(family_id=family.id, category_origin=value or "settings")
        await message.edit_text(
            t(language,"custom.enter_name"),
            reply_markup=custom_create_cancel_keyboard(language,value or "settings"),
        )
    elif action == "custom_create_cancel":
        pending = await state.get_data()
        if (
            key
            and pending.get("family_id") == family.id
            and pending.get("custom_category_id") == int(key)
        ):
            await delete_custom_category(family.id,int(key))
        await state.clear()
        await show_category_list(message,family,value or "settings")
    elif action == "custom_card":
        if not await show_custom_category_card(message, family, int(key), value or "settings"):
            await callback.answer(t(language,"category.not_found"),show_alert=True);return
    elif action == "custom_icon":
        origin,icon=value.split("|",1)
        if key:
            result = await update_custom_category(family.id,int(key),icon=icon)
            if result.status != "updated":
                await callback.answer(t(language,f"custom.{result.status}"),show_alert=True);return
            await state.clear()
            await show_custom_category_card(message,family,int(key),origin)
        else:
            data=await state.get_data(); result=await create_custom_category(family.id,data.get("custom_name"),icon)
            if result.status!="created": await callback.answer(t(language,f"custom.{result.status}"),show_alert=True);return
            await state.set_state(CategorySettingsState.waiting_for_custom_keywords);await state.update_data(custom_category_id=result.category.id)
            await message.edit_text(
                f"<b>{t(language, 'category.bulk_title')}</b>\n\n"
                f"{t(language, 'category.bulk_prompt')}\n\n"
                f"{t(language, 'category.bulk_example')}\n\n"
                f"{t(language, 'category.bulk_max')}",
                parse_mode="HTML",
                reply_markup=custom_create_cancel_keyboard(
                    language,origin,result.category.id,
                ),
            )
    elif action == "custom_icon_picker":
        await message.edit_text(
            t(language,"custom.choose_icon"),
            reply_markup=icon_keyboard(language,value or "settings",key),
        )
    elif action == "custom_other_icon":
        await state.set_state(CategorySettingsState.waiting_for_edit_icon if key else CategorySettingsState.waiting_for_custom_icon)
        await state.update_data(custom_category_id=int(key) if key else None,category_origin=value)
        await message.edit_text(
            t(language,"custom.enter_icon"),
            reply_markup=custom_manual_icon_cancel_keyboard(key,language,value),
        )
    elif action == "custom_edit_name":
        await state.set_state(CategorySettingsState.waiting_for_edit_name)
        await state.update_data(custom_category_id=int(key),family_id=family.id,category_origin=value)
        await message.edit_text(
            t(language,"custom.enter_name"),
            reply_markup=custom_input_cancel_keyboard(key,language,value),
        )
    elif action == "custom_edit_icon":
        await state.set_state(CategorySettingsState.waiting_for_edit_icon)
        await state.update_data(custom_category_id=int(key),family_id=family.id,category_origin=value)
        await message.edit_text(
            t(language,"custom.choose_icon"),reply_markup=icon_keyboard(language,value,key),
        )
    elif action == "custom_add":
        await state.set_state(CategorySettingsState.waiting_for_custom_keywords);await state.update_data(custom_category_id=int(key),family_id=family.id,category_origin=value)
        await message.edit_text(
            f"<b>{t(language, 'category.bulk_title')}</b>\n\n"
            f"{t(language, 'category.bulk_prompt')}\n\n"
            f"{t(language, 'category.bulk_example')}\n\n"
            f"{t(language, 'category.bulk_max')}",
            parse_mode="HTML",reply_markup=custom_input_cancel_keyboard(key,language,value),
        )
    elif action == "custom_remove":
        cat=await get_custom_category(family.id,int(key)); entries=cat.keywords if cat else []
        await message.edit_text(t(language,"category.choose_disable"),reply_markup=keyword_pages_keyboard("custom_remove",key,entries,0,language,value))
    elif action == "custom_remove_one":
        origin,page,index=value.split("|");cat=await get_custom_category(family.id,int(key))
        if cat and int(index)<len(cat.keywords):await remove_custom_keyword(family.id,int(key),cat.keywords[int(index)].normalized_keyword)
        await show_category_list(message,family,origin)
    elif action in {"custom_disable","custom_restore"}:
        await set_custom_category_active(family.id,int(key),action=="custom_restore");await show_category_list(message,family,value)
    elif action == "custom_delete":
        result=await delete_custom_category(family.id,int(key))
        if result=="in_use":await callback.answer(t(language,"custom.in_use"),show_alert=True);return
        await show_category_list(message,family,value)
    elif action == "custom_archive":
        archived=await list_custom_categories(family.id,False)
        await message.edit_text(
            t(language,"custom.archive"),
            reply_markup=custom_archive_keyboard(archived,language,value or "settings"),
        )
    elif action == "custom_ops":
        origin,period,offset=value.split("|"); start,end,all_time=_period("all" if period=="all" else (f"{date.today().year}-{date.today().month:02d}" if period=="current" else period))
        cat=await get_custom_category(family.id,int(key)); tx,total,amount=await get_transactions_by_category_page(family.id,"",20,int(offset),start,end,int(key))
        heading=t(language,"category.all_time") if all_time else f"{month_name(language,start.month)} {start.year}"
        lines=[f"<b>{escape(cat.icon)} {escape(cat.name)} • {heading}</b>",""]+[f"{x.id} {escape(x.title)} -{format_money(x.amount,family_currency(family))} {escape(x.user_name)} {x.created_at:%d.%m.%Y}" for x in tx]
        lines += ["",f"💸 {t(language,'category.total')}: {format_money(amount,family_currency(family))}",f"🧾 {t(language,'common.operations')}: {total}"]
        await message.edit_text("\n".join(lines),parse_mode="HTML",reply_markup=operations_keyboard(key,start.year if start else date.today().year,start.month if start else date.today().month,int(offset),total,language,origin,all_time))
    else:
        await callback.answer(t(language, "category.not_found"), show_alert=True)
        return
    if "analytics-" in value:
        refresh_temporary_message(message, ttl=family.temporary_screen_ttl)
    await callback.answer()


@router.message(CategorySettingsState.waiting_for_keyword)
async def save_category_keyword(message: Message, state: FSMContext):
    data = await state.get_data()
    family = await _family(message)
    language = family_language(family)
    key = data.get("category_key")
    origin = data.get("category_origin", "settings")
    if family.id != data.get("family_id") or key not in EDITABLE_CATEGORY_KEYS:
        await state.clear()
        await message.answer(t(language, "category.not_found"))
        return
    keyword_text = message.text or ""
    if not normalize_keyword(keyword_text.replace(",", " ")):
        await message.answer(t(language, "category.invalid"), reply_markup=cancel_add_keyboard(key, language, origin))
        return
    result = await add_family_keywords(family.id, key, keyword_text)
    if result.limit_exceeded:
        await message.answer(
            t(language, "category.bulk_limit"),
            reply_markup=cancel_add_keyboard(key, language, origin), parse_mode="HTML",
        )
        return
    await state.clear()
    entries = await get_effective_keywords(family.id, key)
    lines = await keyword_result_summary(family, result.items, include_restored=True)
    lines.extend([
        "",
        f"<b>{escape(_category_title(key, language))}</b>",
        f"🔑 {t(language, 'category.keyword_count', count=len(entries))}",
    ])
    await message.answer(
        "\n".join(lines), reply_markup=category_card_keyboard(
            key, language, 0, origin=origin, total=len(entries),
        ),
        parse_mode="HTML",
    )

@router.message(CategorySettingsState.waiting_for_custom_name)
async def custom_name(message: Message,state:FSMContext):
    data=await state.get_data();family=await _family(message);language=family_language(family)
    name=(message.text or "").strip()
    if not name or len(name)>50:await message.answer(t(language,"custom.invalid"));return
    await state.set_state(CategorySettingsState.waiting_for_custom_icon);await state.update_data(custom_name=name)
    await message.answer(t(language,"custom.choose_icon"),reply_markup=icon_keyboard(language,data.get("category_origin","settings")))

@router.message(CategorySettingsState.waiting_for_custom_icon)
@router.message(CategorySettingsState.waiting_for_edit_icon)
async def custom_icon_input(message:Message,state:FSMContext):
    data=await state.get_data();family=await _family(message);language=family_language(family);icon=(message.text or "").strip()
    if not icon or len(icon)>16:await message.answer(t(language,"custom.invalid"));return
    cid=data.get("custom_category_id")
    if cid:
        result=await update_custom_category(family.id,cid,icon=icon)
        if result.status!="updated":await message.answer(t(language,f"custom.{result.status}"));return
        await state.clear()
        await answer_custom_category_card(message,family,cid,data.get("category_origin","settings"),t(language,"custom.updated"))
    else:
        result=await create_custom_category(family.id,data.get("custom_name"),icon)
        if result.status!="created":await message.answer(t(language,f"custom.{result.status}"));return
        cid=result.category.id
        await state.set_state(CategorySettingsState.waiting_for_custom_keywords)
        await state.update_data(custom_category_id=cid)
        await message.answer(
            f"<b>{t(language, 'category.bulk_title')}</b>\n\n"
            f"{t(language, 'category.bulk_prompt')}\n\n"
            f"{t(language, 'category.bulk_example')}\n\n"
            f"{t(language, 'category.bulk_max')}",
            parse_mode="HTML",
            reply_markup=custom_create_cancel_keyboard(
                language,data.get("category_origin","settings"),cid,
            ),
        )

@router.message(CategorySettingsState.waiting_for_edit_name)
async def custom_edit_name(message:Message,state:FSMContext):
    data=await state.get_data();family=await _family(message);language=family_language(family)
    result=await update_custom_category(family.id,data.get("custom_category_id"),name=message.text or "")
    if result.status!="updated":await message.answer(t(language,f"custom.{result.status}"));return
    await state.clear()
    await answer_custom_category_card(message,family,result.category.id,data.get("category_origin","settings"),t(language,"custom.updated"))

@router.message(CategorySettingsState.waiting_for_custom_keywords)
async def custom_keywords_input(message:Message,state:FSMContext):
    data=await state.get_data();family=await _family(message);language=family_language(family);cid=data.get("custom_category_id")
    result=await add_custom_keywords(family.id,cid,message.text or "")
    if result.get("limit_exceeded") or result.get("category_limit"):await message.answer(t(language,"custom.keyword_limit"));return
    await state.clear()
    summary = await keyword_result_summary(family,result.get("items",[]),include_restored=False)
    await answer_custom_category_card(
        message,family,cid,data.get("category_origin","settings"),"\n".join(summary),
    )
