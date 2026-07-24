import re

from app.data.categories import CATEGORIES
from app.services.category_service import detect_category


def is_income(title: str):

    text = title.lower()

    for keyword in CATEGORIES["income"]["keywords"]:
        if keyword in text:
            return True

    return False


def normalize(text: str) -> str:

    text = text.strip()

    text = text.replace(",", ".")

    text = re.sub(r"\s+", " ", text)

    return text


def parse_message(text: str):

    text = normalize(text)

    # --------------------------------------------------
    # ДОХОД
    # --------------------------------------------------

    income = re.match(
        r"^\+(\d+(?:\.\d+)?)(?:\s*(?:€|Є|eur|EUR|евро)?)?(?:\s+(.*))?$",
        text,
        flags=re.IGNORECASE,
    )

    if income:

        amount = float(income.group(1))

        title = income.group(2) or "Доход"

        title = title.strip()

        icon, category = detect_category(
            title,
            "income",
        )

        return {
            "type": "income",
            "title": title,
            "amount": amount,
            "category": f"{icon} {category}",
        }

    # --------------------------------------------------
    # РАСХОД
    # --------------------------------------------------

    expense = re.search(
        r"(\d+(?:\.\d+)?)",
        text,
    )

    if expense:

        amount = float(expense.group(1))

        start = expense.start()

        title = text[:start].strip()

        if not title:
            return None

        title = re.sub(
            r"(€|Є|eur|EUR|евро)\s*$",
            "",
            title,
            flags=re.IGNORECASE,
        ).strip()

        transaction_type = (
            "income"
            if is_income(title)
            else "expense"
        )

        icon, category = detect_category(
            title,
            transaction_type,
        )

        return {
            "type": transaction_type,
            "title": title,
            "amount": amount,
            "category": f"{icon} {category}",
        }

    return None