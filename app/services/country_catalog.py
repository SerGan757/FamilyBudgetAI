from dataclasses import dataclass


@dataclass(frozen=True)
class CountrySetting:
    code: str
    name: str
    flag: str
    currency: str
    timezone: str


COUNTRIES = (
    CountrySetting("DE", "Германия", "🇩🇪", "EUR", "Europe/Berlin"),
    CountrySetting("AT", "Австрия", "🇦🇹", "EUR", "Europe/Vienna"),
    CountrySetting("IT", "Италия", "🇮🇹", "EUR", "Europe/Rome"),
    CountrySetting("ES", "Испания", "🇪🇸", "EUR", "Europe/Madrid"),
    CountrySetting("FR", "Франция", "🇫🇷", "EUR", "Europe/Paris"),
    CountrySetting("NL", "Нидерланды", "🇳🇱", "EUR", "Europe/Amsterdam"),
    CountrySetting("BE", "Бельгия", "🇧🇪", "EUR", "Europe/Brussels"),
    CountrySetting("SK", "Словакия", "🇸🇰", "EUR", "Europe/Bratislava"),
    CountrySetting("PT", "Португалия", "🇵🇹", "EUR", "Europe/Lisbon"),
    CountrySetting("UA", "Украина", "🇺🇦", "UAH", "Europe/Kyiv"),
    CountrySetting("PL", "Польша", "🇵🇱", "PLN", "Europe/Warsaw"),
    CountrySetting("CZ", "Чехия", "🇨🇿", "CZK", "Europe/Prague"),
    CountrySetting("RO", "Румыния", "🇷🇴", "RON", "Europe/Bucharest"),
    CountrySetting("BG", "Болгария", "🇧🇬", "EUR", "Europe/Sofia"),
    CountrySetting("GB", "Великобритания", "🇬🇧", "GBP", "Europe/London"),
    CountrySetting("CH", "Швейцария", "🇨🇭", "CHF", "Europe/Zurich"),
    CountrySetting("HU", "Венгрия", "🇭🇺", "HUF", "Europe/Budapest"),
    CountrySetting("SE", "Швеция", "🇸🇪", "SEK", "Europe/Stockholm"),
    CountrySetting("NO", "Норвегия", "🇳🇴", "NOK", "Europe/Oslo"),
    CountrySetting("DK", "Дания", "🇩🇰", "DKK", "Europe/Copenhagen"),
)
COUNTRIES_BY_CODE = {country.code: country for country in COUNTRIES}
COUNTRY_CODES = frozenset(COUNTRIES_BY_CODE)


def get_country(code: str | None) -> CountrySetting | None:
    return COUNTRIES_BY_CODE.get(code or "")
