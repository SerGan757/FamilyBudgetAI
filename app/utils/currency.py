from numbers import Real


DEFAULT_CURRENCY = "EUR"
CURRENCY_SYMBOLS = {
    "EUR": "€",
    "USD": "$",
    "UAH": "₴",
    "GBP": "£",
    "PLN": "zł",
    "CZK": "Kč",
    "RON": "lei",
    "CHF": "CHF",
    "HUF": "Ft",
    "SEK": "kr",
    "NOK": "kr",
    "DKK": "kr",
}
CURRENCY_CODES = frozenset(CURRENCY_SYMBOLS)


def normalize_currency_code(currency_code: str | None) -> str:
    code = (currency_code or "").strip().upper()
    return code if code in CURRENCY_SYMBOLS else DEFAULT_CURRENCY


def currency_symbol(currency_code: str | None) -> str:
    return CURRENCY_SYMBOLS[normalize_currency_code(currency_code)]


def family_currency(family) -> str:
    return normalize_currency_code(getattr(family, "currency", None))


def format_money(amount: Real, currency_code: str | None = DEFAULT_CURRENCY) -> str:
    number = f"{float(amount):,.2f}".replace(",", " ")
    return f"{number} {currency_symbol(currency_code)}"


def format_signed_money(
    amount: Real,
    currency_code: str | None = DEFAULT_CURRENCY,
    *,
    sign: str | None = None,
) -> str:
    value = float(amount)
    prefix = sign if sign is not None else ("+" if value >= 0 else "-")
    return f"{prefix}{format_money(abs(value), currency_code)}"
