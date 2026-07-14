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

    return None