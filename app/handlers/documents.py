from html import escape
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from app.handlers.document_states import DocumentState
from app.i18n import all_texts, normalize_language, t
from app.i18n.documents import category_display_name
from app.keyboards.documents import *
from app.keyboards.documents import _b
from app.services.document_service import *
from app.services.settings_service import get_current_family_settings

router=Router()
async def _lang(uid):
    data=await get_current_family_settings(uid); return normalize_language(data.get("language") if data else None)
async def show_documents(message, uid):
    language=await _lang(uid); categories=await ensure_default_categories(uid) or []
    await message.edit_text(f"📂 <b>{t(language,'documents.title')}</b>\n\n{t(language,'documents.intro')}",reply_markup=documents_keyboard(categories,language),parse_mode="HTML")
async def show_category(message,uid,cid):
    language=await _lang(uid); category=await get_category(uid,cid); docs=await list_documents(uid,cid)
    if not category or docs is None: await message.edit_text(t(language,"documents.not_found")); return
    display_name = category_display_name(language, category)
    await message.edit_text(f"{category.emoji} <b>{escape(display_name.upper())}</b>\n\n{t(language,'documents.count',count=len(docs))}"+(f"\n\n{t(language,'documents.empty')}" if not docs else ""),reply_markup=category_keyboard(category,docs,language),parse_mode="HTML")

@router.message(F.text.in_(all_texts("menu.documents")))
async def documents_menu(message:Message):
    language=await _lang(message.from_user.id); categories=await ensure_default_categories(message.from_user.id) or []
    await message.answer(f"📂 <b>{t(language,'documents.title')}</b>\n\n{t(language,'documents.intro')}",reply_markup=documents_keyboard(categories,language),parse_mode="HTML")

@router.callback_query(DocumentCallback.filter())
async def document_callback(callback:CallbackQuery,callback_data:DocumentCallback,state:FSMContext):
    m=callback.message; uid=callback.from_user.id; a=callback_data.action; v=callback_data.value; language=await _lang(uid)
    if not m: return await callback.answer()
    if a=="list": await state.clear(); await show_documents(m,uid)
    elif a=="settings":
        await state.clear()
        from app.handlers.settings import _show_current_settings
        await _show_current_settings(m, uid)
    elif a=="category": await state.clear(); await show_category(m,uid,v)
    elif a in {"manage","archive"}:
        cats=await list_categories(uid,active=a=="manage") or []; await m.edit_text(f"⚙️ <b>{t(language,'documents.categories_title')}</b>",reply_markup=manage_keyboard(cats,language,a=="archive"),parse_mode="HTML")
    elif a=="category_admin":
        c=await get_category(uid,v); await m.edit_text(f"{c.emoji} <b>{escape(category_display_name(language,c))}</b>",reply_markup=category_admin_keyboard(c,language),parse_mode="HTML") if c else await m.edit_text(t(language,"documents.not_found"))
    elif a=="new_category": await state.clear(); await state.set_state(DocumentState.category_name); await m.edit_text(t(language,"documents.enter_category"))
    elif a=="emoji":
        data=await state.get_data()
        try: c=await create_category(uid,data["category_name"],EMOJIS[v]); await state.clear(); await m.edit_text(t(language,"documents.category_created")); await show_documents(m,uid)
        except DuplicateCategoryError: await m.edit_text(t(language,"documents.duplicate_category"))
    elif a in {"up","down"}: await move_category(uid,v,-1 if a=="up" else 1); c=await get_category(uid,v); await m.edit_text(f"{c.emoji} <b>{escape(category_display_name(language,c))}</b>",reply_markup=category_admin_keyboard(c,language),parse_mode="HTML")
    elif a=="toggle_category":
        c=await get_category(uid,v); c=await update_category(uid,v,is_active=not c.is_active); await m.edit_text(f"{c.emoji} <b>{escape(category_display_name(language,c))}</b>",reply_markup=category_admin_keyboard(c,language),parse_mode="HTML")
    elif a=="delete_category":
        try: await delete_category(uid,v); await show_documents(m,uid)
        except CategoryNotEmptyError: await callback.answer(t(language,"documents.not_empty"),show_alert=True)
        except LastCategoryError: await callback.answer(t(language,"documents.last_category"),show_alert=True)
    elif a in {"rename","change_emoji"}:
        await state.clear(); await state.update_data(category_id=v)
        if a=="rename": await state.set_state(DocumentState.rename); await m.edit_text(t(language,"documents.enter_category"))
        else: await m.edit_text(t(language,"documents.choose_emoji"),reply_markup=emoji_keyboard("replace_emoji"))
    elif a=="replace_emoji":
        data=await state.get_data(); c=await update_category(uid,data["category_id"],emoji=EMOJIS[v]); await state.clear(); await m.edit_text(f"{c.emoji} <b>{escape(category_display_name(language,c))}</b>",reply_markup=category_admin_keyboard(c,language),parse_mode="HTML")
    elif a=="new_document": await state.clear(); await state.update_data(category_id=v); await state.set_state(DocumentState.title); await m.edit_text(t(language,"documents.enter_title"))
    elif a.startswith("owner_"):
        if a=="owner_other": await state.set_state(DocumentState.custom_owner); await m.edit_text(t(language,"documents.enter_owner"))
        else: await state.update_data(owner={"owner_me":t(language,"documents.owner_me")[2:],"owner_family":t(language,"documents.owner_family")[2:],"owner_car":t(language,"documents.owner_car")[2:]}[a]); await state.set_state(DocumentState.access); await m.edit_text(t(language,"documents.access"),reply_markup=access_keyboard(language))
    elif a.startswith("access_"): await state.update_data(access_level=a.removeprefix("access_"),files=[]); await state.set_state(DocumentState.files); await m.edit_text(t(language,"documents.send_file"))
    elif a=="add_file": await m.edit_text(t(language,"documents.send_file"))
    elif a=="save":
        data=await state.get_data(); doc=await create_document(uid,data["category_id"],data["title"],data.get("owner"),data["access_level"],data.get("files",[])); await state.clear(); await m.edit_text(t(language,"documents.saved")); await show_category(m,uid,doc.category_id)
    elif a=="cancel": await state.clear(); await show_documents(m,uid)
    elif a=="document":
        d=await get_document(uid,v)
        if not d: await callback.answer(t(language,"documents.private_denied"),show_alert=True)
        else: await m.edit_text(f"{d.category.emoji} <b>{escape(d.title)}</b>\n\n{t(language,'documents.category')}: {escape(category_display_name(language,d.category))}\n{t(language,'documents.owner_label')}: {escape(d.owner_name or '—')}\n📎 {t(language,'documents.files',count=len(d.files))}\n{t(language,'documents.access_label')}: {t(language,'documents.access_private' if d.access_level=='private' else 'documents.access_family')}\n{t(language,'documents.added')}: {d.created_at:%d.%m.%Y}",reply_markup=document_keyboard(d,language),parse_mode="HTML")
    elif a=="get":
        d=await get_document(uid,v)
        if not d: await callback.answer(t(language,"documents.private_denied"),show_alert=True)
        else:
            for f in d.files:
                if f.file_type=="photo": await m.answer_photo(f.telegram_file_id)
                else: await m.answer_document(f.telegram_file_id)
    elif a=="delete_document":
        d=await get_document(uid,v); cid=d.category_id if d else 0
        if await delete_document(uid,v): await callback.answer(t(language,"documents.deleted")); await show_category(m,uid,cid)
    elif a=="search": await state.clear(); await state.set_state(DocumentState.search); await m.edit_text(t(language,"documents.search_prompt"))
    await callback.answer()

@router.message(DocumentState.category_name)
async def category_name(message:Message,state:FSMContext):
    language=await _lang(message.from_user.id)
    try: name=validate_category_name(message.text or "")
    except ValueError: return await message.answer(t(language,"documents.invalid_name"))
    await state.update_data(category_name=name); await state.set_state(DocumentState.category_emoji); await message.answer(t(language,"documents.choose_emoji"),reply_markup=emoji_keyboard())
@router.message(DocumentState.rename)
async def rename_category(message:Message,state:FSMContext):
    language=await _lang(message.from_user.id); data=await state.get_data()
    try: c=await update_category(message.from_user.id,data["category_id"],name=message.text or "")
    except (ValueError,DuplicateCategoryError): return await message.answer(t(language,"documents.invalid_name"))
    await state.clear(); await message.answer(f"{c.emoji} {escape(category_display_name(language,c))}",reply_markup=category_admin_keyboard(c,language))
@router.message(DocumentState.title)
async def document_title(message:Message,state:FSMContext):
    language=await _lang(message.from_user.id)
    try: title=validate_title(message.text or "")
    except ValueError: return await message.answer(t(language,"documents.invalid_name"))
    await state.update_data(title=title); await state.set_state(DocumentState.owner); await message.answer(t(language,"documents.owner"),reply_markup=owner_keyboard(language))
@router.message(DocumentState.custom_owner)
async def custom_owner(message:Message,state:FSMContext):
    language=await _lang(message.from_user.id); owner=(message.text or "").strip()
    if not owner or len(owner)>100: return await message.answer(t(language,"documents.invalid_name"))
    await state.update_data(owner=owner); await state.set_state(DocumentState.access); await message.answer(t(language,"documents.access"),reply_markup=access_keyboard(language))
@router.message(DocumentState.files)
async def receive_file(message:Message,state:FSMContext):
    language=await _lang(message.from_user.id); item=None
    if message.photo:
        f=message.photo[-1]; item={"telegram_file_id":f.file_id,"telegram_file_unique_id":f.file_unique_id,"file_type":"photo","original_filename":None,"mime_type":"image/jpeg"}
    elif message.document and message.document.mime_type in ALLOWED_MIME_TYPES:
        f=message.document; item={"telegram_file_id":f.file_id,"telegram_file_unique_id":f.file_unique_id,"file_type":"document","original_filename":f.file_name,"mime_type":f.mime_type}
    if not item: return await message.answer(t(language,"documents.invalid_file"))
    data=await state.get_data(); files=data.get("files",[]); files.append(item); await state.update_data(files=files); await message.answer(t(language,"documents.file_added"),reply_markup=files_keyboard(language))
@router.message(DocumentState.search)
async def search(message:Message,state:FSMContext):
    language=await _lang(message.from_user.id); docs=await search_documents(message.from_user.id,message.text or "") or []; await state.clear()
    rows=[[_b(f"📄 {d.title}","document",d.id)] for d in docs]+[[_b(t(language,"nav.back"),"list")]]
    from aiogram.types import InlineKeyboardMarkup
    await message.answer(t(language,"documents.search_empty") if not docs else f"🔍 {len(docs)}",reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
