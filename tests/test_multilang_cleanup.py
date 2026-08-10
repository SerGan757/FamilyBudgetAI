import unittest
from types import SimpleNamespace

from app.handlers.settings import about_text
from app.i18n import t
from app.keyboards.projects import (
    pending_project_keyboard,
    project_back_keyboard,
    project_cancel_keyboard,
)
from app.keyboards.recurring_inline import delete_keyboard


def keyboard_texts(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


class MultilangCleanupTests(unittest.TestCase):
    def test_delete_recurring_and_project_flow_texts_are_localized(self):
        self.assertEqual(t("uk", "delete.instruction"), "Введіть ID операції.")
        self.assertEqual(t("de", "recurring.edit_title"), "Vorlage bearbeiten")
        self.assertEqual(t("en", "projects.no_transactions"), "There are no operations yet.")

    def test_recurring_delete_keyboard_uses_requested_language(self):
        self.assertIn("Delete", keyboard_texts(delete_keyboard(7, "en"))[0])
        self.assertNotIn("Удал", keyboard_texts(delete_keyboard(7, "en"))[0])

    def test_project_secondary_keyboards_use_requested_language(self):
        self.assertTrue(any("Zum Projekt" in text for text in keyboard_texts(project_back_keyboard(2, "de"))))
        self.assertIn("Cancel", keyboard_texts(project_cancel_keyboard("en"))[0])
        pending = pending_project_keyboard(SimpleNamespace(id=3, name="Home"), "uk")
        texts = keyboard_texts(pending)
        self.assertIn("Без проєкту", texts)
        self.assertIn("❌ Скасувати", texts)

    def test_about_has_localized_annotated_examples_and_savings_goal(self):
        for language in ("uk", "de", "en"):
            text = about_text(language)
            self.assertIn("++500", text)
            self.assertIn("#", text)
            self.assertIn("<i>", text)
            self.assertNotIn("кофе 5", text)
        self.assertIn("Sparziel", about_text("de"))
        self.assertIn("ціл", about_text("uk").lower())

    def test_callback_data_remains_language_independent(self):
        uk = project_back_keyboard(11, "uk").inline_keyboard[0][0].callback_data
        de = project_back_keyboard(11, "de").inline_keyboard[0][0].callback_data
        self.assertEqual(uk, de)


if __name__ == "__main__":
    unittest.main()
