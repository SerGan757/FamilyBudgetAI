import re

CATEGORIES = {
    "кофе": "☕ Кафе",
    "cafe": "☕ Кафе",
    "lidl": "🛒 Продукты",
    "aldi": "🛒 Продукты",
    "rewe": "🛒 Продукты",
    "edeka": "🛒 Продукты",
    "kaufland": "🛒 Продукты",
    "заправка": "⛽ Автомобиль",
    "shell": "⛽ Автомобиль",
    "aral": "⛽ Автомобиль",
    "esso": "⛽ Автомобиль",
}


def detect_category(title: str):
    text = title.lower()

    for key, category in CATEGORIES.items():
        if key in text:
            return category

    return "📦 Другое"


def parse_message(text: str):
    text = text.strip()

    income = re.match(r"^\+?\s*(\d+(?:[.,]\d+)?)\s+(.+)$", text)
    if income:
        amount = float(income.group(1).replace(",", "."))
        title = income.group(2)

        return {
            "type": "income",
            "title": title,
            "amount": amount,
            "category": "💰 Доход",
        }

    expense = re.match(r"^(.+?)\s+(\d+(?:[.,]\d+)?)$", text)
    if expense:
        title = expense.group(1)
        amount = float(expense.group(2).replace(",", "."))

        return {
            "type": "expense",
            "title": title,
            "amount": amount,
            "category": detect_category(title),
        }

    return None