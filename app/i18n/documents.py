from app.i18n.translations import SUPPORTED_LANGUAGES

_EN = {
 "menu.documents":"📂 Documents", "documents.title":"DOCUMENTS", "documents.intro":"Quick access to family documents. Files stay in Telegram and can be retrieved for viewing, sharing or printing.",
 "documents.add_category":"➕ Add category", "documents.manage":"⚙️ Manage categories", "documents.search":"🔍 Find document", "documents.archive":"🗃 Archive",
 "documents.empty":"No documents yet.", "documents.count":"Documents: {count}", "documents.add_document":"➕ Add document", "documents.edit_category":"✏️ Edit category",
 "documents.enter_category":"Enter the new category name.\n\nExamples:\nBank\nSchool\nTaxes", "documents.choose_emoji":"Choose an emoji.", "documents.category_created":"✅ Category created",
 "documents.invalid_name":"Enter a non-empty name up to 80 characters.", "documents.duplicate_category":"A category with this name already exists.", "documents.categories_title":"DOCUMENT CATEGORIES",
 "documents.rename":"✏️ Rename", "documents.emoji":"😀 Change icon", "documents.up":"⬆️ Up", "documents.down":"⬇️ Down", "documents.archive_action":"🗃 Archive", "documents.restore":"♻️ Restore", "documents.delete":"🗑 Delete",
 "documents.not_empty":"A category containing documents cannot be deleted.", "documents.last_category":"The last available category cannot be deleted.", "documents.enter_title":"Enter the document title.",
 "documents.owner":"Who owns this document?", "documents.owner_me":"👤 Me", "documents.owner_family":"👨‍👩‍👧‍👦 Family", "documents.owner_car":"🚗 Car", "documents.owner_other":"✏️ Other",
 "documents.enter_owner":"Enter the owner name.", "documents.access":"Choose access:", "documents.access_family":"👨‍👩‍👧‍👦 Family", "documents.access_private":"🔒 Only me",
 "documents.send_file":"📎 Send a photo, an image as a file, or a PDF.", "documents.file_added":"✅ File added.", "documents.add_file":"➕ Add another file", "documents.save":"✅ Save document", "documents.cancel":"❌ Cancel",
 "documents.saved":"✅ Document saved", "documents.files":"Files: {count}", "documents.category":"Category", "documents.owner_label":"Owner", "documents.access_label":"Access", "documents.added":"Added",
 "documents.get":"📎 Get document", "documents.private_denied":"🔒 This document is available only to its owner.", "documents.invalid_file":"Send a Telegram photo, PDF, JPEG, PNG or WEBP file.",
 "documents.search_prompt":"Enter part of the document title.", "documents.search_empty":"No documents found.", "documents.not_found":"Document or category not found.", "documents.deleted":"Document deleted.", "documents.operation_finished":"This operation has already finished.",
}

_RU = {
 "menu.documents":"📂 Документы", "documents.title":"ДОКУМЕНТЫ", "documents.intro":"Быстрый доступ к семейным документам. Файлы хранятся в Telegram и доступны для просмотра, отправки или печати.",
 "documents.add_category":"➕ Добавить категорию", "documents.manage":"⚙️ Управление категориями", "documents.search":"🔍 Найти документ", "documents.archive":"🗃 Архив", "documents.empty":"Пока список пуст.", "documents.count":"Документов: {count}",
 "documents.add_document":"➕ Добавить документ", "documents.edit_category":"✏️ Изменить категорию", "documents.enter_category":"Введите название новой категории.\n\nПримеры:\nБанк\nШкола\nНалоги", "documents.choose_emoji":"Выберите emoji.", "documents.category_created":"✅ Категория создана",
 "documents.invalid_name":"Введите непустое название до 80 символов.", "documents.duplicate_category":"Категория с таким названием уже существует.", "documents.categories_title":"КАТЕГОРИИ ДОКУМЕНТОВ", "documents.rename":"✏️ Переименовать", "documents.emoji":"😀 Изменить значок", "documents.up":"⬆️ Выше", "documents.down":"⬇️ Ниже", "documents.archive_action":"🗃 Архивировать", "documents.restore":"♻️ Восстановить", "documents.delete":"🗑 Удалить", "documents.not_empty":"Нельзя удалить категорию с документами.", "documents.last_category":"Нельзя удалить последнюю доступную категорию.",
 "documents.enter_title":"Введите название документа.", "documents.owner":"Кому принадлежит документ?", "documents.owner_me":"👤 Мне", "documents.owner_family":"👨‍👩‍👧‍👦 Семье", "documents.owner_car":"🚗 Автомобилю", "documents.owner_other":"✏️ Другое", "documents.enter_owner":"Введите владельца.", "documents.access":"Выберите доступ:", "documents.access_family":"👨‍👩‍👧‍👦 Семье", "documents.access_private":"🔒 Только мне", "documents.send_file":"📎 Отправьте фото, изображение как файл или PDF.", "documents.file_added":"✅ Файл добавлен.", "documents.add_file":"➕ Добавить ещё файл", "documents.save":"✅ Сохранить документ", "documents.cancel":"❌ Отмена", "documents.saved":"✅ Документ сохранён", "documents.files":"Файлов: {count}", "documents.category":"Категория", "documents.owner_label":"Владелец", "documents.access_label":"Доступ", "documents.added":"Добавлен", "documents.get":"📎 Получить документ", "documents.private_denied":"🔒 Этот документ доступен только владельцу.", "documents.invalid_file":"Отправьте Telegram-фото либо PDF, JPEG, PNG или WEBP.", "documents.search_prompt":"Введите часть названия документа.", "documents.search_empty":"Документы не найдены.", "documents.not_found":"Документ или категория не найдены.", "documents.deleted":"Документ удалён.", "documents.operation_finished":"Эта операция уже завершена.",
}

DOCUMENT_TEXTS = {language: dict(_EN) for language in SUPPORTED_LANGUAGES}
DOCUMENT_TEXTS["ru"].update(_RU)
# Native main-menu labels; all remaining document strings have a complete English fallback.
for language, label in {"uk":"📂 Документи","de":"📂 Dokumente","be":"📂 Дакументы","pl":"📂 Dokumenty","cs":"📂 Dokumenty","sk":"📂 Dokumenty","ro":"📂 Documente","bg":"📂 Документи","hu":"📂 Dokumentumok"}.items():
    DOCUMENT_TEXTS[language]["menu.documents"] = label

SYSTEM_CATEGORY_NAMES = {
    "ru": {"personal":"Личные документы","family":"Семья","car":"Автомобиль","housing":"Жильё","germany":"Германия / ведомства","medicine":"Медицина","work":"Работа","trips":"Поездки","other":"Прочее"},
    "uk": {"personal":"Особисті документи","family":"Сім’я","car":"Автомобіль","housing":"Житло","germany":"Німеччина / відомства","medicine":"Медицина","work":"Робота","trips":"Подорожі","other":"Інше"},
    "de": {"personal":"Persönliche Dokumente","family":"Familie","car":"Auto","housing":"Wohnen","germany":"Deutschland / Behörden","medicine":"Medizin","work":"Arbeit","trips":"Reisen","other":"Sonstiges"},
    "en": {"personal":"Personal documents","family":"Family","car":"Car","housing":"Housing","germany":"Germany / authorities","medicine":"Medicine","work":"Work","trips":"Trips","other":"Other"},
    "be": {"personal":"Асабістыя дакументы","family":"Сям’я","car":"Аўтамабіль","housing":"Жыллё","germany":"Германія / установы","medicine":"Медыцына","work":"Праца","trips":"Паездкі","other":"Іншае"},
    "pl": {"personal":"Dokumenty osobiste","family":"Rodzina","car":"Samochód","housing":"Mieszkanie","germany":"Niemcy / urzędy","medicine":"Medycyna","work":"Praca","trips":"Podróże","other":"Inne"},
    "cs": {"personal":"Osobní dokumenty","family":"Rodina","car":"Automobil","housing":"Bydlení","germany":"Německo / úřady","medicine":"Zdravotnictví","work":"Práce","trips":"Cesty","other":"Ostatní"},
    "sk": {"personal":"Osobné dokumenty","family":"Rodina","car":"Automobil","housing":"Bývanie","germany":"Nemecko / úrady","medicine":"Zdravotníctvo","work":"Práca","trips":"Cesty","other":"Ostatné"},
    "ro": {"personal":"Documente personale","family":"Familie","car":"Automobil","housing":"Locuință","germany":"Germania / autorități","medicine":"Medicină","work":"Muncă","trips":"Călătorii","other":"Altele"},
    "bg": {"personal":"Лични документи","family":"Семейство","car":"Автомобил","housing":"Жилище","germany":"Германия / институции","medicine":"Медицина","work":"Работа","trips":"Пътувания","other":"Други"},
    "hu": {"personal":"Személyes dokumentumok","family":"Család","car":"Autó","housing":"Lakhatás","germany":"Németország / hatóságok","medicine":"Egészségügy","work":"Munka","trips":"Utazások","other":"Egyéb"},
}

def category_display_name(language, category):
    """Prefer a user override; otherwise translate a stable system code."""
    if category.name:
        return category.name
    code = getattr(category, "code", None)
    return SYSTEM_CATEGORY_NAMES.get(language, SYSTEM_CATEGORY_NAMES["en"]).get(code, code or "—")
