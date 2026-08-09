import unittest
from types import SimpleNamespace

from app.handlers.history import format_transaction as format_history_transaction
from app.handlers.settings import about_text, family_settings_text
from app.handlers.statistics import analytics_keyboard, day_keyboard, month_keyboard
from app.i18n import category_label, family_language, month_name, normalize_language, t
from app.keyboards.main_menu import main_menu_keyboard
from app.keyboards.settings_menu import family_settings_keyboard_for_ttl


class MultilangV1Tests(unittest.TestCase):
    def test_supported_languages_build_complete_main_menu(self):
        for language in ("ru", "uk", "de", "en", "be"):
            keyboard = main_menu_keyboard(language)
            self.assertEqual([len(row) for row in keyboard.keyboard], [2, 2, 2, 2])
            self.assertEqual(keyboard.keyboard[0][0].text, t(language, "menu.history"))
            self.assertEqual(keyboard.keyboard[-1][-1].text, t(language, "menu.settings"))
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
        self.assertIn("Sprache", keyboard.inline_keyboard[0][0].text)
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


if __name__ == "__main__":
    unittest.main()
