import unittest
from types import SimpleNamespace

from app.handlers.projects import project_card_text, projects_help_text
from app.handlers.settings import about_text
from app.handlers.start import welcome_text
from app.i18n import t
from app.i18n.translations import SUPPORTED_LANGUAGES
from app.keyboards.projects import ProjectCallback, projects_keyboard
from app.keyboards.settings_menu import family_settings_keyboard_for_ttl


def button_texts(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


class ProjectIconConsistencyTests(unittest.TestCase):
    def test_settings_separates_categories_and_projects_in_all_locales(self):
        for language in SUPPORTED_LANGUAGES:
            with self.subTest(language=language):
                self.assertTrue(t(language, "settings.categories").startswith("🏷"))
                self.assertTrue(t(language, "settings.projects").startswith("📁"))
                texts = button_texts(family_settings_keyboard_for_ttl(20, language))
                self.assertIn(t(language, "settings.categories"), texts)
                self.assertIn(t(language, "settings.projects"), texts)

    def test_project_main_card_and_button_use_folder(self):
        project = SimpleNamespace(id=7, name="Italy 2026", tag="italy", is_active=True)
        self.assertTrue(projects_help_text("en").startswith("📁"))
        self.assertTrue(project_card_text(project, 10, 1, "EUR", "en").startswith("📁"))
        keyboard = projects_keyboard([project], 1, 0, active=True, language="en")
        first = keyboard.inline_keyboard[0][0]
        self.assertTrue(first.text.startswith("📁"))
        callback = ProjectCallback.unpack(first.callback_data)
        self.assertEqual((callback.action, callback.project_id), ("card", 7))

    def test_about_and_start_use_folder_for_projects(self):
        family = SimpleNamespace(language="en", currency="EUR")
        for text in (about_text("en"), welcome_text(family)):
            self.assertIn("📁 Project:", text)
            self.assertIn("#renovation", text)
            self.assertNotIn("🏷 Project:", text)
        self.assertIn("🎯", about_text("en"))


if __name__ == "__main__":
    unittest.main()
