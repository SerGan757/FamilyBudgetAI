from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.data.categories import CATEGORIES
from app.i18n import category_label, t
from app.services.category_override_service import SETTINGS_CATEGORY_KEYS, stored_category_for_key


class CategoryCallback(CallbackData, prefix="cat"):
    action: str
    key: str = ""
    value: str = ""


def button(text: str, action: str, key: str = "", value: str = ""):
    return InlineKeyboardButton(
        text=text, callback_data=CategoryCallback(action=action, key=key, value=value).pack(),
    )


def categories_keyboard(catalog, language: str, *, origin: str = "settings"):
    rows = []
    for key in SETTINGS_CATEGORY_KEYS:
        label = category_label(language, stored_category_for_key(key))
        count = len(catalog.get(key, []))
        suffix = "" if key == "other" else f" — {count}"
        rows.append([button(f"{label}{suffix}", "card", key, origin)])
    if origin.startswith("analytics-"):
        _, year, month = origin.split("-")
        rows.append([InlineKeyboardButton(
            text=t(language, "category.back_analytics"),
            callback_data=f"analytics_back:{year}:{month}",
        )])
    else:
        from app.keyboards.settings_menu import FamilySettingsCallback
        rows.append([InlineKeyboardButton(
            text=t(language, "nav.back"),
            callback_data=FamilySettingsCallback(action="home", value="").pack(),
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_card_keyboard(
    key: str, language: str, page: int, *, origin: str, total: int = 0,
):
    rows = []
    pages = []
    if page > 0:
        pages.append(button("⬅️", "card", key, f"{origin}|{page-1}"))
    if (page + 1) * 15 < total:
        pages.append(button("➡️", "card", key, f"{origin}|{page+1}"))
    if pages:
        rows.append(pages)
    if key != "other":
        rows.extend([
            [button(t(language, "category.add"), "add", key, origin)],
            [button(t(language, "category.disable"), "disable", key, f"{origin}|{page}")],
            [button(t(language, "category.restore"), "disabled", key, origin)],
        ])
    rows.append([button(t(language, "category.operations"), "ops", key, f"{origin}|current|0")])
    rows.append([button(t(language, "nav.back"), "list", value=origin)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def keyword_pages_keyboard(action: str, key: str, entries, page: int, language: str, origin: str, per_page=15):
    last = max(0, (len(entries) - 1) // per_page)
    page = min(max(page, 0), last)
    start = page * per_page
    rows = [
        [button(entry.keyword, f"{action}_one", key, f"{origin}|{page}|{index}")]
        for index, entry in enumerate(entries[start:start + per_page], start=start)
    ]
    navigation = []
    if page > 0:
        navigation.append(button("⬅️", action, key, f"{origin}|{page-1}"))
    if page < last:
        navigation.append(button("➡️", action, key, f"{origin}|{page+1}"))
    if navigation:
        rows.append(navigation)
    rows.append([button(t(language, "nav.back"), "card", key, origin)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_add_keyboard(key: str, language: str, origin: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [button(t(language, "goal.cancel"), "card", key, origin)],
    ])


def operations_keyboard(key: str, year: int, month: int, offset: int, total: int, language: str, origin: str, all_time=False):
    from app.handlers.statistics import _shift_month
    rows = []
    if not all_time:
        py, pm = _shift_month(year, month, -1)
        ny, nm = _shift_month(year, month, 1)
        rows.append([
            button(t(language, "nav.prev_month"), "ops", key, f"{origin}|{py:04d}-{pm:02d}|0"),
            button(t(language, "nav.next_month"), "ops", key, f"{origin}|{ny:04d}-{nm:02d}|0"),
        ])
    pages = []
    if offset > 0:
        pages.append(button("⬅️", "ops", key, f"{origin}|{'all' if all_time else f'{year:04d}-{month:02d}'}|{max(0, offset-20)}"))
    if offset + 20 < total:
        pages.append(button("➡️", "ops", key, f"{origin}|{'all' if all_time else f'{year:04d}-{month:02d}'}|{offset+20}"))
    if pages:
        rows.append(pages)
    if not all_time:
        rows.append([button(t(language, "category.all_time"), "ops", key, f"{origin}|all|0")])
    rows.append([button(t(language, "category.back_categories"), "list", value=origin)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
