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
)
from app.services.category_override_service import (
    EDITABLE_CATEGORY_KEYS, SETTINGS_CATEGORY_KEYS, add_family_keywords,
    disable_family_keyword, get_disabled_keywords, get_effective_category_catalog,
    get_effective_keywords, normalize_keyword, restore_family_keyword,
    stored_category_for_key,
)
from app.services.family_context_service import require_family_for_chat
from app.services.history_service import get_transactions_by_category_page
from app.utils.currency import family_currency, format_money
from app.utils.temporary_screens import refresh_temporary_message


router = Router()
KEYWORDS_PER_PAGE = 15


def _category_title(key: str, language: str) -> str:
    return category_label(language, stored_category_for_key(key) or "")


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
    await message.edit_text(
        f"🏷 <b>{t(language, 'category.title')}</b>",
        reply_markup=categories_keyboard(catalog, language, origin=origin),
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
    await message.answer(
        f"🏷 <b>{t(family_language(family), 'category.title')}</b>",
        reply_markup=categories_keyboard(catalog, family_language(family)),
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
    if action != "add":
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
    conflicts = [item for item in result.items if item.status == "conflict"]
    lines = [
        f"✅ {t(language, 'category.bulk_added')}: {result.count('added')}",
        f"♻️ {t(language, 'category.bulk_restored')}: {result.count('restored')}",
        f"ℹ️ {t(language, 'category.bulk_existing')}: {result.count('already_exists')}",
        f"⚠️ {t(language, 'category.bulk_conflicting')}: {len(conflicts)}",
    ]
    if conflicts:
        lines.extend(["", f"⚠️ <b>{t(language, 'category.bulk_conflicts')}:</b>"])
        lines.extend(
            f"• {escape(item.keyword)} → {escape(_category_title(item.conflict_category_key, language))}"
            for item in conflicts
        )
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
