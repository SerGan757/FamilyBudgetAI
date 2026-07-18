import re

from app.data.categories import CATEGORIES
from app.services.category_service import detect_category


def is_income(title: str) -> bool:

    text = title.lower()

    for keyword in CATEGORIES["income"]["keywords"]:
        if keyword in text:
            return True

    return False


def parse_message(text: str):

    text = text.strip().replace(",", ".")

    # --------------------------------------------------
    # Доход
    # --------------------------------------------------

    match = re.match(r"^\+?(\d+(?:\.\d+)?)\s+(.+)$", text)

    if match:

        amount = float(match.group(1))
        title = match.group(2).strip()

        transaction_type = (
            "income"
            if is_income(title)
            else "income"
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

    # --------------------------------------------------
    # Расход
    # --------------------------------------------------

    match = re.match(r"^(.+?)\s+(\d+(?:\.\d+)?)$", text)

    if match:

        title = match.group(1).strip()
        amount = float(match.group(2))

        transaction_type = "income" if is_income(title) else "expense"

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
