from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.i18n import t
from app.i18n.documents import category_display_name

class DocumentCallback(CallbackData, prefix="doc"):
    action: str
    value: int = 0

def _b(text, action, value=0):
    return InlineKeyboardButton(text=text, callback_data=DocumentCallback(action=action, value=value).pack())

def documents_keyboard(categories, language="ru"):
    rows = [[_b(f"{c.emoji} {category_display_name(language, c)}", "category", c.id) for c in categories[i:i+2]] for i in range(0, len(categories), 2)]
    rows += [[_b(t(language,"documents.add_category"),"new_category")], [_b(t(language,"documents.manage"),"manage")], [_b(t(language,"documents.search"),"search")], [_b(t(language,"nav.back"),"settings")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def category_keyboard(category, documents, language="ru"):
    rows = [[_b(f"📄 {d.title}", "document", d.id)] for d in documents]
    rows += [[_b(t(language,"documents.add_document"),"new_document",category.id)], [_b(t(language,"documents.edit_category"),"category_admin",category.id)], [_b(t(language,"nav.back"),"list")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def manage_keyboard(categories, language="ru", archived=False):
    rows = [[_b(f"{c.emoji} {category_display_name(language, c)}", "category_admin", c.id)] for c in categories]
    rows += [[_b(t(language,"documents.add_category"),"new_category")], [_b(t(language,"documents.archive") if not archived else t(language,"documents.manage"), "archive" if not archived else "manage")], [_b(t(language,"nav.back"),"list")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def category_admin_keyboard(category, language="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[[_b(t(language,"documents.rename"),"rename",category.id),_b(t(language,"documents.emoji"),"change_emoji",category.id)],[_b(t(language,"documents.up"),"up",category.id),_b(t(language,"documents.down"),"down",category.id)],[_b(t(language,"documents.archive_action") if category.is_active else t(language,"documents.restore"),"toggle_category",category.id)],[_b(t(language,"documents.delete"),"delete_category",category.id)],[_b(t(language,"nav.back"),"manage")]])

EMOJIS=("📁","👤","👨‍👩‍👧‍👦","🚗","🏠","🏦","🎓","🧾","🩺","💼","✈️","🔧")
def emoji_keyboard(action="emoji"):
    return InlineKeyboardMarkup(inline_keyboard=[[_b(e,action,i) for i,e in enumerate(EMOJIS[j:j+4],j)] for j in range(0,len(EMOJIS),4)])
def owner_keyboard(language="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[[_b(t(language,"documents.owner_me"),"owner_me"),_b(t(language,"documents.owner_family"),"owner_family")],[_b(t(language,"documents.owner_car"),"owner_car"),_b(t(language,"documents.owner_other"),"owner_other")],[_b(t(language,"documents.cancel"),"cancel")]])
def access_keyboard(language="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[[_b(t(language,"documents.access_family"),"access_family")],[_b(t(language,"documents.access_private"),"access_private")],[_b(t(language,"documents.cancel"),"cancel")]])
def files_keyboard(language="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[[_b(t(language,"documents.add_file"),"add_file")],[_b(t(language,"documents.save"),"save")],[_b(t(language,"documents.cancel"),"cancel")]])
def document_keyboard(document, language="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[[_b(t(language,"documents.get"),"get",document.id)],[_b(t(language,"documents.delete"),"delete_document",document.id)],[_b(t(language,"nav.back"),"category",document.category_id)]])
