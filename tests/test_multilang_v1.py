import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers.history import format_transaction as format_history_transaction
from app.handlers.settings import about_text, family_settings_text
from app.handlers.statistics import analytics_keyboard, day_keyboard, month_keyboard
from app.i18n import category_label, family_language, month_name, normalize_language, normalize_telegram_language, t
from app.keyboards.main_menu import main_menu_keyboard
from app.keyboards.settings_menu import family_settings_keyboard_for_ttl, language_keyboard_for
from app.services import family_context_service


class MultilangV1Tests(unittest.TestCase):
    def test_supported_languages_build_complete_main_menu(self):
        for language in ("ru", "uk", "de", "en", "be", "pl", "cs", "sk", "ro", "bg", "hu"):
            keyboard = main_menu_keyboard(language)
            self.assertEqual([len(row) for row in keyboard.keyboard], [2, 2, 2, 2])
            self.assertEqual(keyboard.keyboard[0][0].text, t(language, "menu.history"))
            self.assertEqual(keyboard.keyboard[-1][-1].text, t(language, "menu.settings"))
            self.assertNotIn(t(language, "menu.documents"), [button.text for row in keyboard.keyboard for button in row])
            self.assertTrue(keyboard.resize_keyboard)
            self.assertTrue(keyboard.one_time_keyboard)

    def test_unknown_and_empty_language_fall_back_to_russian(self):
        self.assertEqual(normalize_language(None), "ru")
        self.assertEqual(normalize_language("xx"), "ru")
        self.assertEqual(t("xx", "menu.today"), t("ru", "menu.today"))
        self.assertEqual(family_language(SimpleNamespace(language=None)), "ru")

    def test_callback_data_is_language_independent(self):
        for builder, args in (
            (day_keyboard, (__import__("datetime").date(2026, 8, 9), 0, 0)),
            (month_keyboard, (2026, 8, 0, 0)),
            (analytics_keyboard, (2026, 8)),
        ):
            ru = builder(*args, "ru")
            en = builder(*args, "en")
            ru_data = [[button.callback_data for button in row] for row in ru.inline_keyboard]
            en_data = [[button.callback_data for button in row] for row in en.inline_keyboard]
            self.assertEqual(ru_data, en_data)
            self.assertNotEqual(ru.inline_keyboard[0][0].text, en.inline_keyboard[0][0].text)

    def test_settings_and_about_use_selected_language(self):
        data = {"language": "de", "currency": "EUR", "country": None,
                "city": "Berlin", "timezone": "Europe/Berlin", "temporary_screen_ttl": 20}
        self.assertIn("Familieneinstellungen", family_settings_text(data))
        keyboard = family_settings_keyboard_for_ttl(20, "de")
        self.assertTrue(any(
            "Sprache" in button.text
            for row in keyboard.inline_keyboard for button in row
        ))
        self.assertIn("Über den Bot", about_text("de"))

    def test_user_data_is_not_translated_and_is_html_safe(self):
        transaction = SimpleNamespace(
            id=7, type="expense", amount=12, is_recurring=False,
            category="🛒 Продукты", title="<X>", user_name="Ann",
            project=None,
        )
        text = format_history_transaction(transaction, "EUR", "en")
        self.assertIn("&lt;X&gt;", text)
        self.assertIn("🛒", text)
        self.assertEqual(category_label("en", "🛒 Продукты"), "🛒 Groceries")

    def test_month_names_are_localized(self):
        self.assertEqual(month_name("en", 8), "August")
        self.assertEqual(month_name("uk", 2), "Лютий")
        self.assertEqual(month_name("xx", 1), "Январь")
        expected = {"pl": "Styczeń", "cs": "Leden", "sk": "Január", "ro": "Ianuarie", "bg": "Януари", "hu": "Január"}
        for language, january in expected.items():
            self.assertEqual(month_name(language, 1), january)

    def test_august_2026_is_localized_for_every_supported_language(self):
        expected = {
            "ru": "Август 2026",
            "uk": "Серпень 2026",
            "de": "August 2026",
            "en": "August 2026",
            "pl": "Sierpień 2026",
            "cs": "Srpen 2026",
            "sk": "August 2026",
            "ro": "August 2026",
            "bg": "Август 2026",
            "hu": "Augusztus 2026",
            "be": "Жнівень 2026",
        }
        for language, title in expected.items():
            self.assertEqual(f"{month_name(language, 8)} 2026", title)

    def test_selected_language_is_marked(self):
        keyboard = language_keyboard_for("de")
        labels = [row[0].text for row in keyboard.inline_keyboard[:-1]]
        self.assertIn("✅ 🇩🇪 Deutsch", labels)
        self.assertEqual(sum(label.startswith("✅ ") for label in labels), 1)

    def test_telegram_locale_normalization(self):
        expected = {"de-DE":"de", "de":"de", "pl-PL":"pl", "uk-UA":"uk", "en-GB":"en", "cs-CZ":"cs", "fr-FR":"ru"}
        for locale, language in expected.items():
            self.assertEqual(normalize_telegram_language(locale), language)

    def test_european_languages_cover_core_screens_and_help(self):
        for language in ("pl", "cs", "sk", "ro", "bg", "hu"):
            for key in (
                "menu.title", "settings.title", "balance.title", "analytics.title",
                "analytics.help_title", "analytics.help", "about.title",
                "about.description", "about.features_text",
            ):
                value = t(language, key)
                self.assertTrue(value)
                self.assertNotEqual(value, key)
                self.assertNotEqual(value, t("ru", key))

class InitialFamilyLanguageTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_family_language_is_never_overwritten_by_telegram_locale(self):
        family = SimpleNamespace(id=7, language="uk")
        with patch.object(
            family_context_service, "get_family_by_chat_id", AsyncMock(return_value=family),
        ):
            result = await family_context_service.get_or_create_family_for_chat(
                123, "Family", initial_language="de",
            )
        self.assertIs(result, family)
        self.assertEqual(family.language, "uk")


if __name__ == "__main__":
    unittest.main()
