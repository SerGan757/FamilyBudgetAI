import re
from math import isfinite

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

# Deliberately narrower than the single-operation parser: no signs, tags,
# embedded numeric names, currency suffixes, date syntax, or phone-sized digits.
MULTI_AMOUNT = re.compile(r"(?:0|[1-9][0-9]{0,5})(?:[.,][0-9]{1,2})?")
MULTI_WORD = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", re.UNICODE)
QUANTITY_UNITS = frozenset({"kg", "g", "mg", "l", "ml", "cl", "pcs", "pc", "x",
                            "кг", "г", "мг", "л", "мл", "шт", "штук"})
# These labels commonly introduce an identifier, date, or model number. In
# multi-input prefer rejection to interpreting that number as a price.
NUMBER_LABELS = frozenset({"номер", "number", "дата", "date", "телефон", "phone",
                           "iphone", "айфон", "ipad", "galaxy", "pixel",
                           "витамин", "vitamin", "рейс", "flight", "маршрут", "route"})


def split_multi_expenses(text: str) -> list[str] | None:
    """Return complete description/amount pairs, or nothing; never a prefix.

    This is only a lexical quick-input format. Single-operation parsing and
    category/project interpretation remain in their existing service paths.
    """
    pairs = []
    description = []
    for token in normalize(text).split():
        if MULTI_AMOUNT.fullmatch(token):
            if not description or float(token.replace(",", ".")) <= 0:
                return None
            if any(word.casefold() in NUMBER_LABELS for word in description):
                return None
            pairs.append(" ".join([*description, token]))
            description = []
        elif (MULTI_WORD.fullmatch(token) and token.casefold() not in QUANTITY_UNITS
              and not re.fullmatch(CURRENCY, token, re.IGNORECASE)):
            description.append(token)
        else:
            return None
    return pairs if len(pairs) >= 2 and not description else None


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


def is_financial_handoff(text: str) -> bool:
    """Conservative, read-only recognition for leaving a saved upload.

    Use the canonical single/multi/project grammars; saving and authorization
    still belong to the normal expenses handler. In a document conversation,
    an amount-first expense with an unknown description is ambiguous (e.g.
    '123 abc xyz'), even though ordinary quick input accepts that format.
    """
    from app.services.project_service import extract_project_tag

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    has_multi = has_project = has_goal = False
    other = CATEGORIES["other"]
    for line in lines:
        try:
            transaction_text, project_tag = extract_project_tag(line)
        except ValueError:
            return False
        if "#" in line and project_tag is None:
            return False
        parsed = parse_message(transaction_text)
        parts = None if parsed is not None or project_tag else split_multi_expenses(line)
        if parsed is None and parts is None:
            return False
        has_multi = has_multi or parts is not None
        has_project = has_project or project_tag is not None
        operations = [parse_message(part) for part in parts] if parts else [parsed]
        for operation in operations:
            if (operation is None or not isfinite(operation["amount"])
                    or operation["amount"] <= 0 or len(operation["title"]) > 255):
                return False
            has_goal = has_goal or operation["type"] == "goal_contribution"
        if (parsed is not None and parsed["type"] == "expense" and not project_tag
                and AMOUNT_FIRST.fullmatch(normalize(transaction_text))
                and parsed["category"] == f"{other['icon']} {other['title']}"):
            return False
    # The existing batch save path does not mix projects or goals with multi.
    return bool(lines) and not (has_multi and (has_project or has_goal))
