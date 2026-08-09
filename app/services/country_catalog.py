from dataclasses import dataclass


@dataclass(frozen=True)
class CountrySetting:
    code: str
    name: str
    flag: str
    currency: str
    timezone: str

    default_language: str = "en"


COUNTRIES = (
    CountrySetting("DE", "Германия", "🇩🇪", "EUR", "Europe/Berlin", "de"),
    CountrySetting("AT", "Австрия", "🇦🇹", "EUR", "Europe/Vienna"),
    CountrySetting("IT", "Италия", "🇮🇹", "EUR", "Europe/Rome"),
    CountrySetting("ES", "Испания", "🇪🇸", "EUR", "Europe/Madrid"),
    CountrySetting("FR", "Франция", "🇫🇷", "EUR", "Europe/Paris"),
    CountrySetting("NL", "Нидерланды", "🇳🇱", "EUR", "Europe/Amsterdam"),
    CountrySetting("BE", "Бельгия", "🇧🇪", "EUR", "Europe/Brussels"),
    CountrySetting("SK", "Словакия", "🇸🇰", "EUR", "Europe/Bratislava", "sk"),
    CountrySetting("PT", "Португалия", "🇵🇹", "EUR", "Europe/Lisbon"),
    CountrySetting("UA", "Украина", "🇺🇦", "UAH", "Europe/Kyiv", "uk"),
    CountrySetting("PL", "Польша", "🇵🇱", "PLN", "Europe/Warsaw", "pl"),
    CountrySetting("CZ", "Чехия", "🇨🇿", "CZK", "Europe/Prague", "cs"),
    CountrySetting("RO", "Румыния", "🇷🇴", "RON", "Europe/Bucharest", "ro"),
    CountrySetting("BG", "Болгария", "🇧🇬", "EUR", "Europe/Sofia", "bg"),
    CountrySetting("GB", "Великобритания", "🇬🇧", "GBP", "Europe/London", "en"),
    CountrySetting("CH", "Швейцария", "🇨🇭", "CHF", "Europe/Zurich"),
    CountrySetting("HU", "Венгрия", "🇭🇺", "HUF", "Europe/Budapest", "hu"),
    CountrySetting("SE", "Швеция", "🇸🇪", "SEK", "Europe/Stockholm"),
    CountrySetting("NO", "Норвегия", "🇳🇴", "NOK", "Europe/Oslo"),
    CountrySetting("DK", "Дания", "🇩🇰", "DKK", "Europe/Copenhagen"),
    CountrySetting("US", "США", "🇺🇸", "USD", "America/New_York", "en"),
    CountrySetting("BY", "Беларусь", "🇧🇾", "EUR", "Europe/Minsk", "be"),
)
COUNTRIES_BY_CODE = {country.code: country for country in COUNTRIES}
COUNTRY_CODES = frozenset(COUNTRIES_BY_CODE)

COUNTRY_DEFAULT_LANGUAGES = {
    "DE": "de", "UA": "uk", "PL": "pl", "CZ": "cs", "SK": "sk",
    "RO": "ro", "BG": "bg", "HU": "hu", "GB": "en", "US": "en",
    "BY": "be",
}


def get_country(code: str | None) -> CountrySetting | None:
    return COUNTRIES_BY_CODE.get(code or "")


def get_country_default_language(code: str | None) -> str:
    return COUNTRY_DEFAULT_LANGUAGES.get(code or "", "en")
