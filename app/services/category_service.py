from app.data.categories import CATEGORIES


def detect_category(title: str, transaction_type: str = "expense"):

    text = title.lower().strip()

    if transaction_type == "income":
        category = CATEGORIES["income"]
        return category["icon"], category["title"]

    best = CATEGORIES["other"]
    best_score = 0

    for key, category in CATEGORIES.items():

        if key == "income":
            continue

        score = 0

        for keyword in category["keywords"]:

            keyword = keyword.lower()

            # Полное совпадение
            if text == keyword:
                score += 100

            # Совпадение по слову
            elif keyword in text:
                score += 10

        if score > best_score:
            best_score = score
            best = category

    return (
        best["icon"],
        best["title"],
    )


async def detect_category_for_family(
    family_id: int,
    title: str,
    transaction_type: str = "expense",
    *,
    session=None,
):
    """Apply the established scoring algorithm to one family's effective catalog."""
    if transaction_type == "income":
        category = CATEGORIES["income"]
        return category["icon"], category["title"]

    from app.services.category_override_service import get_effective_category_catalog

    text = title.lower().strip()
    catalog = await get_effective_category_catalog(family_id, session=session)
    best_key = "other"
    best_score = 0
    for key, category in CATEGORIES.items():
        if key == "income":
            continue
        score = 0
        for entry in catalog.get(key, []):
            keyword = entry.normalized_keyword
            if text == keyword:
                score += 100
            elif keyword in text:
                score += 10
        if score > best_score:
            best_score = score
            best_key = key
    best = CATEGORIES[best_key]
    return best["icon"], best["title"]


async def detect_category_reference_for_family(family_id: int, title: str, transaction_type="expense"):
    icon, label = await detect_category_for_family(family_id, title, transaction_type)
    if transaction_type == "income": return icon, label, None
    from app.services.custom_category_service import detect_custom_category
    custom, custom_score = await detect_custom_category(family_id, title)
    # System wins equal scores, preserving the established category order.
    if custom is None: return icon, label, None
    text=title.lower().strip(); system_score=0
    from app.services.category_override_service import get_effective_category_catalog
    catalog=await get_effective_category_catalog(family_id)
    for entries in catalog.values():
        score=sum(100 if text==e.normalized_keyword else 10 if e.normalized_keyword in text else 0 for e in entries)
        system_score=max(system_score,score)
    if custom_score>system_score:return custom.icon,custom.name,custom.id
    return icon,label,None


def detect_subcategory(title: str):

    text = title.lower()

    # ---------- Доход ----------

    if "зарплата" in text:
        return "Зарплата"

    if "аванс" in text:
        return "Аванс"

    if "премия" in text:
        return "Премия"

    if "дивиденд" in text:
        return "Дивиденды"

    if "подработка" in text:
        return "Подработка"

    if "нашел" in text or "нашёл" in text:
        return "Находка"

    if "возврат" in text:
        return "Возврат"

    # ---------- Автомобиль ----------

    if "shell" in text or "aral" in text or "esso" in text:
        return "Топливо"

    if "мойка" in text:
        return "Мойка"

    if "ремонт" in text:
        return "Ремонт"

    if "страховка" in text:
        return "Страховка"

    if "шины" in text:
        return "Шины"

    # ---------- Дом ----------

    if "интернет" in text:
        return "Интернет"

    if "аренда" in text:
        return "Аренда"

    if "газ" in text:
        return "Газ"

    if "электричество" in text:
        return "Электричество"

    if "вода" in text:
        return "Вода"

    # ---------- Дети ----------

    if "ксюша" in text:
        return "Ксюша"

    if "никита" in text:
        return "Никита"

    if "владик" in text:
        return "Владик"


# ---------- Животные ----------

    if "животн" in text:
        return "Животные"

    if "питом" in text:
        return "Животные"

    if "кот" in text:
        return "Животные"

    if "кошка" in text:
        return "Животные"

    if "пёс" in text or "пес" in text:
        return "Животные"

    if "собак" in text:
        return "Животные"

    if "щенок" in text:
        return "Животные"

    if "корм" in text:
        return "Животные"

    if "purina" in text:
        return "Животные"

    if "whiskas" in text:
        return "Животные"

    if "felix" in text:
        return "Животные"

    if "sheba" in text:
        return "Животные"

    if "royal canin" in text:
        return "Животные"

    if "brit" in text:
        return "Животные"

    if "pro plan" in text:
        return "Животные"

    if "perfect fit" in text:
        return "Животные"

    if "наполнитель" in text:
        return "Животные"

    if "песок" in text:
        return "Животные"

    if "лоток" in text:
        return "Животные"

    if "вет" in text:
        return "Животные"

    if "ветеринар" in text:
        return "Животные"

    if "ветклиника" in text:
        return "Животные"

    if "привив" in text:
        return "Животные"

    if "вакцин" in text:
        return "Животные"

    if "блох" in text:
        return "Животные"

    if "клещ" in text:
        return "Животные"

    if "глист" in text:
        return "Животные"

    if "ошейник" in text:
        return "Животные"

    if "поводок" in text:
        return "Животные"

    if "намордник" in text:
        return "Животные"

    if "миска" in text:
        return "Животные"

    if "игрушк" in text:
        return "Животные"

    if "когтеточка" in text:
        return "Животные"

    if "лежанка" in text:
        return "Животные"

    if "переноска" in text:
        return "Животные"

    if "стерилизац" in text:
        return "Животные"

    if "кастрац" in text:
        return "Животные"

    return None
