import re

from app.data.categories import CATEGORIES
from app.services.category_service import detect_category


NUMBER = r"\d+(?:[.,]\d+)?"
CURRENCY = r"(?:€|\$|₴|£|₽|Є|zł|Kč|lei|CHF|Ft|kr|eur|евро)"

GOAL_CONTRIBUTION = re.compile(
    rf"^\+\+\s*(?P<amount>{NUMBER})(?:\s*{CURRENCY})?(?:\s+.*)?$",
    re.IGNORECASE,
)
AMOUNT_FIRST = re.compile(
    rf"^(?P<income>\+)?\s*(?P<amount>{NUMBER})(?:\s*{CURRENCY})?(?:\s+(?P<title>.+))?$",
    re.IGNORECASE,
)
AMOUNT_LAST = re.compile(
    rf"^(?P<title>.+?)\s+(?P<income>\+)?\s*(?P<amount>{NUMBER})(?:\s*{CURRENCY})?$",
    re.IGNORECASE,
)
# Preserve the established alternative form: "+ salary 2000".
INCOME_PREFIX = re.compile(
    rf"^\+\s*(?P<title>.+?)\s+(?P<amount>{NUMBER})(?:\s*{CURRENCY})?$",
    re.IGNORECASE,
)
NUMBER_TOKEN = re.compile(rf"(?<![\w.,]){NUMBER}(?![\w.,])")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()


def is_income(title: str) -> bool:
    text = title.lower()
    return any(keyword in text for keyword in CATEGORIES["income"]["keywords"])


def make_result(transaction_type: str, title: str, amount: float):
    title = clean_title(title)
    if not title:
        title = "Доход" if transaction_type == "income" else "Расход"
    icon, category = detect_category(title, transaction_type)
    return {
        "type": transaction_type,
        "title": title,
        "amount": amount,
        "category": f"{icon} {category}",
    }


def parse_message(text: str):
    text = normalize(text)
    if not text:
        return None

    # Goal syntax must win over the ordinary single-plus income marker.
    goal = GOAL_CONTRIBUTION.fullmatch(text)
    if goal:
        return {
            "type": "goal_contribution",
            "title": "",
            "amount": float(goal.group("amount").replace(",", ".")),
            "category": None,
        }

    # A normal quick-input operation must contain exactly one amount. This
    # prevents choosing one value from ambiguous input such as "10 lunch 20".
    if len(NUMBER_TOKEN.findall(text)) != 1:
        return None

    match = AMOUNT_FIRST.fullmatch(text)
    if match:
        transaction_type = "income" if match.group("income") else "expense"
        return make_result(
            transaction_type,
            match.group("title") or "",
            float(match.group("amount").replace(",", ".")),
        )

    match = INCOME_PREFIX.fullmatch(text)
    if match:
        return make_result(
            "income",
            match.group("title"),
            float(match.group("amount").replace(",", ".")),
        )

    match = AMOUNT_LAST.fullmatch(text)
    if match:
        transaction_type = "income" if match.group("income") else "expense"
        return make_result(
            transaction_type,
            match.group("title"),
            float(match.group("amount").replace(",", ".")),
        )

    return None
