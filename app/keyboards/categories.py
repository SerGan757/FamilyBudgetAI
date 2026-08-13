from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.data.categories import CATEGORIES
from app.i18n import category_label, t
from app.services.category_override_service import SETTINGS_CATEGORY_KEYS, stored_category_for_key
from app.services.custom_category_service import ICONS


class CategoryCallback(CallbackData, prefix="cat"):
    action: str
    key: str = ""
    value: str = ""


def button(text: str, action: str, key: str = "", value: str = ""):
    return InlineKeyboardButton(
        text=text, callback_data=CategoryCallback(action=action, key=key, value=value).pack(),
    )


def categories_keyboard(catalog, language: str, *, origin: str = "settings", custom=(), archived=()):
    rows = []
    for key in SETTINGS_CATEGORY_KEYS:
        label = category_label(language, stored_category_for_key(key))
        count = len(catalog.get(key, []))
        suffix = "" if key == "other" else f" — {count}"
        rows.append([button(f"{label}{suffix}", "card", key, origin)])
    if custom:
        rows.append([button(t(language,"custom.mine"), "list", value=origin)])
        rows.extend([[button(f"{c.icon} {c.name}","custom_card",str(c.id),origin)] for c in custom])
    else:
        rows.append([button(t(language,"custom.none"), "list", value=origin)])
    rows.append([button(t(language,"custom.new"),"custom_new",value=origin)])
    if archived: rows.append([button(t(language,"custom.archive"),"custom_archive",value=origin)])
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

def icon_keyboard(language, origin, category_id=""):
    rows=[[button(icon,"custom_icon",category_id,f"{origin}|{icon}") for icon in ICONS[i:i+4]] for i in range(0,len(ICONS),4)]
    rows.append([button(t(language,"custom.other_icon"),"custom_other_icon",category_id,origin)])
    cancel_action = "custom_card" if category_id else "custom_create_cancel"
    rows.append([button(t(language,"goal.cancel"),cancel_action,category_id,origin)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def custom_create_cancel_keyboard(language, origin, category_id=""):
    return InlineKeyboardMarkup(inline_keyboard=[
        [button(
            t(language, "goal.cancel"), "custom_create_cancel",
            str(category_id or ""), origin,
        )],
    ])


def custom_input_cancel_keyboard(category_id, language, origin):
    return InlineKeyboardMarkup(inline_keyboard=[
        [button(t(language, "goal.cancel"), "custom_card", str(category_id), origin)],
    ])


def custom_manual_icon_cancel_keyboard(category_id, language, origin):
    return InlineKeyboardMarkup(inline_keyboard=[
        [button(t(language, "goal.cancel"), "custom_icon_picker", str(category_id or ""), origin)],
    ])


def custom_archive_keyboard(categories, language, origin):
    rows = [
        [button(f"{category.icon} {category.name}", "custom_card", str(category.id), origin)]
        for category in categories
    ]
    rows.append([button(t(language, "nav.back"), "list", value=origin)])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def custom_card_keyboard(category_id, language, origin, archived=False):
    cid=str(category_id)
    if archived:return InlineKeyboardMarkup(inline_keyboard=[
        [button(t(language,"custom.restore"),"custom_restore",cid,origin)],
        [button(t(language,"custom.delete"),"custom_delete",cid,origin)],
        [button(t(language,"nav.back"),"list",value=origin)]])
    return InlineKeyboardMarkup(inline_keyboard=[
        [button(t(language,"custom.edit_name"),"custom_edit_name",cid,origin)],
        [button(t(language,"custom.edit_icon"),"custom_edit_icon",cid,origin)],
        [button(t(language,"category.add"),"custom_add",cid,origin)],
        [button(t(language,"category.disable"),"custom_remove",cid,origin)],
        [button(t(language,"category.operations"),"custom_ops",cid,f"{origin}|current|0")],
        [button(t(language,"custom.disable"),"custom_disable",cid,origin)],
        [button(t(language,"nav.back"),"list",value=origin)]])


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
    back_action = "custom_card" if action.startswith("custom_") else "card"
    rows.append([button(t(language, "nav.back"), back_action, key, origin)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_add_keyboard(key: str, language: str, origin: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [button(t(language, "goal.cancel"), "card", key, origin)],
    ])


def operations_keyboard(key: str, year: int, month: int, offset: int, total: int, language: str, origin: str, all_time=False):
    from app.handlers.statistics import _shift_month
    operation_action = "custom_ops" if str(key).isdigit() else "ops"
    rows = []
    if not all_time:
        py, pm = _shift_month(year, month, -1)
        ny, nm = _shift_month(year, month, 1)
        rows.append([
            button(t(language, "nav.prev_month"), operation_action, key, f"{origin}|{py:04d}-{pm:02d}|0"),
            button(t(language, "nav.next_month"), operation_action, key, f"{origin}|{ny:04d}-{nm:02d}|0"),
        ])
    pages = []
    if offset > 0:
        pages.append(button("⬅️", operation_action, key, f"{origin}|{'all' if all_time else f'{year:04d}-{month:02d}'}|{max(0, offset-20)}"))
    if offset + 20 < total:
        pages.append(button("➡️", operation_action, key, f"{origin}|{'all' if all_time else f'{year:04d}-{month:02d}'}|{offset+20}"))
    if pages:
        rows.append(pages)
    if not all_time:
        rows.append([button(t(language, "category.all_time"), operation_action, key, f"{origin}|all|0")])
    if operation_action == "custom_ops":
        rows.append([button(t(language, "category.back_categories"), "custom_card", str(key), origin)])
    else:
        rows.append([button(t(language, "category.back_categories"), "list", value=origin)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
