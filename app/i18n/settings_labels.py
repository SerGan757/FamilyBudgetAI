from .translations import normalize_language


COUNTRY_NAMES = {
    "ru": ("Германия", "Австрия", "Италия", "Испания", "Франция", "Нидерланды", "Бельгия", "Словакия", "Португалия", "Украина", "Польша", "Чехия", "Румыния", "Болгария", "Великобритания", "Швейцария", "Венгрия", "Швеция", "Норвегия", "Дания", "США", "Беларусь"),
    "uk": ("Німеччина", "Австрія", "Італія", "Іспанія", "Франція", "Нідерланди", "Бельгія", "Словаччина", "Португалія", "Україна", "Польща", "Чехія", "Румунія", "Болгарія", "Велика Британія", "Швейцарія", "Угорщина", "Швеція", "Норвегія", "Данія", "США", "Білорусь"),
    "de": ("Deutschland", "Österreich", "Italien", "Spanien", "Frankreich", "Niederlande", "Belgien", "Slowakei", "Portugal", "Ukraine", "Polen", "Tschechien", "Rumänien", "Bulgarien", "Vereinigtes Königreich", "Schweiz", "Ungarn", "Schweden", "Norwegen", "Dänemark", "USA", "Belarus"),
    "en": ("Germany", "Austria", "Italy", "Spain", "France", "Netherlands", "Belgium", "Slovakia", "Portugal", "Ukraine", "Poland", "Czechia", "Romania", "Bulgaria", "United Kingdom", "Switzerland", "Hungary", "Sweden", "Norway", "Denmark", "United States", "Belarus"),
    "be": ("Германія", "Аўстрыя", "Італія", "Іспанія", "Францыя", "Нідэрланды", "Бельгія", "Славакія", "Партугалія", "Украіна", "Польшча", "Чэхія", "Румынія", "Балгарыя", "Вялікабрытанія", "Швейцарыя", "Венгрыя", "Швецыя", "Нарвегія", "Данія", "ЗША", "Беларусь"),
    "pl": ("Niemcy", "Austria", "Włochy", "Hiszpania", "Francja", "Niderlandy", "Belgia", "Słowacja", "Portugalia", "Ukraina", "Polska", "Czechy", "Rumunia", "Bułgaria", "Wielka Brytania", "Szwajcaria", "Węgry", "Szwecja", "Norwegia", "Dania", "Stany Zjednoczone", "Białoruś"),
    "cs": ("Německo", "Rakousko", "Itálie", "Španělsko", "Francie", "Nizozemsko", "Belgie", "Slovensko", "Portugalsko", "Ukrajina", "Polsko", "Česko", "Rumunsko", "Bulharsko", "Spojené království", "Švýcarsko", "Maďarsko", "Švédsko", "Norsko", "Dánsko", "Spojené státy", "Bělorusko"),
    "sk": ("Nemecko", "Rakúsko", "Taliansko", "Španielsko", "Francúzsko", "Holandsko", "Belgicko", "Slovensko", "Portugalsko", "Ukrajina", "Poľsko", "Česko", "Rumunsko", "Bulharsko", "Spojené kráľovstvo", "Švajčiarsko", "Maďarsko", "Švédsko", "Nórsko", "Dánsko", "Spojené štáty", "Bielorusko"),
    "ro": ("Germania", "Austria", "Italia", "Spania", "Franța", "Țările de Jos", "Belgia", "Slovacia", "Portugalia", "Ucraina", "Polonia", "Cehia", "România", "Bulgaria", "Regatul Unit", "Elveția", "Ungaria", "Suedia", "Norvegia", "Danemarca", "Statele Unite", "Belarus"),
    "bg": ("Германия", "Австрия", "Италия", "Испания", "Франция", "Нидерландия", "Белгия", "Словакия", "Португалия", "Украйна", "Полша", "Чехия", "Румъния", "България", "Обединеното кралство", "Швейцария", "Унгария", "Швеция", "Норвегия", "Дания", "САЩ", "Беларус"),
    "hu": ("Németország", "Ausztria", "Olaszország", "Spanyolország", "Franciaország", "Hollandia", "Belgium", "Szlovákia", "Portugália", "Ukrajna", "Lengyelország", "Csehország", "Románia", "Bulgária", "Egyesült Királyság", "Svájc", "Magyarország", "Svédország", "Norvégia", "Dánia", "Egyesült Államok", "Fehéroroszország"),
}

COUNTRY_CODES = ("DE", "AT", "IT", "ES", "FR", "NL", "BE", "SK", "PT", "UA", "PL", "CZ", "RO", "BG", "GB", "CH", "HU", "SE", "NO", "DK", "US", "BY")
COUNTRY_INDEX = {code: index for index, code in enumerate(COUNTRY_CODES)}

TIMEZONE_CITIES = {
    "ru": ("Берлин", "Киев", "Варшава", "Прага", "Вена", "Рим", "Мадрид", "Париж", "Амстердам", "Брюссель", "Братислава", "Лиссабон", "Бухарест", "София", "Лондон", "Цюрих", "Будапешт", "Стокгольм", "Осло", "Копенгаген", "Нью-Йорк", "Минск", "UTC"),
    "uk": ("Берлін", "Київ", "Варшава", "Прага", "Відень", "Рим", "Мадрид", "Париж", "Амстердам", "Брюссель", "Братислава", "Лісабон", "Бухарест", "Софія", "Лондон", "Цюрих", "Будапешт", "Стокгольм", "Осло", "Копенгаген", "Нью-Йорк", "Мінськ", "UTC"),
    "de": ("Berlin", "Kyjiw", "Warschau", "Prag", "Wien", "Rom", "Madrid", "Paris", "Amsterdam", "Brüssel", "Bratislava", "Lissabon", "Bukarest", "Sofia", "London", "Zürich", "Budapest", "Stockholm", "Oslo", "Kopenhagen", "New York", "Minsk", "UTC"),
    "en": ("Berlin", "Kyiv", "Warsaw", "Prague", "Vienna", "Rome", "Madrid", "Paris", "Amsterdam", "Brussels", "Bratislava", "Lisbon", "Bucharest", "Sofia", "London", "Zurich", "Budapest", "Stockholm", "Oslo", "Copenhagen", "New York", "Minsk", "UTC"),
    "be": ("Берлін", "Кіеў", "Варшава", "Прага", "Вена", "Рым", "Мадрыд", "Парыж", "Амстэрдам", "Брусель", "Браціслава", "Лісабон", "Бухарэст", "Сафія", "Лондан", "Цюрых", "Будапешт", "Стакгольм", "Осла", "Капенгаген", "Нью-Ёрк", "Мінск", "UTC"),
    "pl": ("Berlin", "Kijów", "Warszawa", "Praga", "Wiedeń", "Rzym", "Madryt", "Paryż", "Amsterdam", "Bruksela", "Bratysława", "Lizbona", "Bukareszt", "Sofia", "Londyn", "Zurych", "Budapeszt", "Sztokholm", "Oslo", "Kopenhaga", "Nowy Jork", "Mińsk", "UTC"),
    "cs": ("Berlín", "Kyjev", "Varšava", "Praha", "Vídeň", "Řím", "Madrid", "Paříž", "Amsterdam", "Brusel", "Bratislava", "Lisabon", "Bukurešť", "Sofie", "Londýn", "Curych", "Budapešť", "Stockholm", "Oslo", "Kodaň", "New York", "Minsk", "UTC"),
    "sk": ("Berlín", "Kyjev", "Varšava", "Praha", "Viedeň", "Rím", "Madrid", "Paríž", "Amsterdam", "Brusel", "Bratislava", "Lisabon", "Bukurešť", "Sofia", "Londýn", "Zürich", "Budapešť", "Štokholm", "Oslo", "Kodaň", "New York", "Minsk", "UTC"),
    "ro": ("Berlin", "Kiev", "Varșovia", "Praga", "Viena", "Roma", "Madrid", "Paris", "Amsterdam", "Bruxelles", "Bratislava", "Lisabona", "București", "Sofia", "Londra", "Zürich", "Budapesta", "Stockholm", "Oslo", "Copenhaga", "New York", "Minsk", "UTC"),
    "bg": ("Берлин", "Киев", "Варшава", "Прага", "Виена", "Рим", "Мадрид", "Париж", "Амстердам", "Брюксел", "Братислава", "Лисабон", "Букурещ", "София", "Лондон", "Цюрих", "Будапеща", "Стокхолм", "Осло", "Копенхаген", "Ню Йорк", "Минск", "UTC"),
    "hu": ("Berlin", "Kijev", "Varsó", "Prága", "Bécs", "Róma", "Madrid", "Párizs", "Amszterdam", "Brüsszel", "Pozsony", "Lisszabon", "Bukarest", "Szófia", "London", "Zürich", "Budapest", "Stockholm", "Oslo", "Koppenhága", "New York", "Minszk", "UTC"),
}

TIMEZONE_VALUES = ("Europe/Berlin", "Europe/Kyiv", "Europe/Warsaw", "Europe/Prague", "Europe/Vienna", "Europe/Rome", "Europe/Madrid", "Europe/Paris", "Europe/Amsterdam", "Europe/Brussels", "Europe/Bratislava", "Europe/Lisbon", "Europe/Bucharest", "Europe/Sofia", "Europe/London", "Europe/Zurich", "Europe/Budapest", "Europe/Stockholm", "Europe/Oslo", "Europe/Copenhagen", "America/New_York", "Europe/Minsk", "UTC")
TIMEZONE_INDEX = {value: index for index, value in enumerate(TIMEZONE_VALUES)}


def country_name(language: str, code: str) -> str:
    index = COUNTRY_INDEX.get(code)
    if index is None:
        return code
    return COUNTRY_NAMES[normalize_language(language)][index]


def timezone_name(language: str, value: str) -> str:
    index = TIMEZONE_INDEX.get(value)
    if index is None:
        return value
    labels = TIMEZONE_CITIES.get(normalize_language(language), TIMEZONE_CITIES["en"])
    return labels[index]
