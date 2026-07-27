import re

from app.data.categories import CATEGORIES
from app.services.category_service import detect_category


CURRENCY = r"(?:€|Є|eur|EUR|евро)?"

NUMBER = r"\d+(?:[.,]\d+)?"

INCOME_FIRST = re.compile(
    rf"""
    ^\+
    \s*
    (?P<amount>{NUMBER})
    \s*
    {CURRENCY}
    \s*
    (?P<title>.*)$
    """,
    re.IGNORECASE | re.VERBOSE,
)

INCOME_LAST = re.compile(
    rf"""
    ^
    (?P<title>.*?)
    \s*
    \+
    \s*
    (?P<amount>{NUMBER})
    \s*
    {CURRENCY}
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

EXPENSE = re.compile(
    rf"""
    ^
    (?P<title>.*?)
    \s*
    (?P<amount>{NUMBER})
    \s*
    {CURRENCY}
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def normalize(text: str) -> str:

    text = text.strip()

    text = text.replace(",", ".")

    text = re.sub(r"\s+", " ", text)

    return text


def clean_title(title: str) -> str:

    title = re.sub(
        r"(€|Є|eur|EUR|евро)$",
        "",
        title,
        flags=re.IGNORECASE,
    )

    title = title.replace("+", " ")

    title = re.sub(r"\s+", " ", title)

    return title.strip()


def is_income(title: str) -> bool:

    text = title.lower()

    for keyword in CATEGORIES["income"]["keywords"]:

        if keyword in text:
            return True

    return False


def make_result(
    transaction_type: str,
    title: str,
    amount: float,
):

    title = clean_title(title)

    if not title:

        title = (
            "Доход"
            if transaction_type == "income"
            else "Расход"
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


def parse_message(text: str):

    text = normalize(text)

    # -----------------------------
    # ДОХОД
    # -----------------------------

    income = re.search(
        r"^(.*?)(?:\s*)\+(?:\s*)(\d+(?:\.\d+)?)(?:\s*(?:€|Є|eur|EUR|евро)?)?$",
        text,
        flags=re.IGNORECASE,
    )

    if income:

        title = income.group(1).strip()

        amount = float(income.group(2))

        if not title:
            title = "Доход"

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

    income = re.search(
        r"^\+(\d+(?:\.\d+)?)(?:\s*(?:€|Є|eur|EUR|евро)?)?(?:\s*(.*))?$",
        text,
        flags=re.IGNORECASE,
    )

    if income:

        amount = float(income.group(1))

        title = (income.group(2) or "Доход").strip()

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

    # -----------------------------
    # РАСХОД
    # -----------------------------

    expense = re.search(
        r"^(.*?)(\d+(?:\.\d+)?)(?:\s*(?:€|Є|eur|EUR|евро)?)?$",
        text,
        flags=re.IGNORECASE,
    )

    if expense:

        title = expense.group(1).strip()

        amount = float(expense.group(2))

        if not title:
            return None

        title = re.sub(
            r"[+]+",
            "",
            title,
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