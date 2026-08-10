import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers import savings_goal
from app.handlers.projects import project_card_text
from app.handlers.settings import family_settings_text
from app.i18n import country_name, t, timezone_name
from app.keyboards.projects import project_cancel_keyboard
from app.keyboards.savings_goal import GoalCallback, goal_edit_cancel_keyboard
from app.keyboards.settings_menu import (
    FamilySettingsCallback, country_keyboard, currency_keyboard_for,
    timezone_keyboard_for,
)


class SettingsLabelRegressionTests(unittest.TestCase):
    def test_german_country_screen_has_localized_labels(self):
        labels = [row[0].text for row in country_keyboard(0, "de").inline_keyboard[:10]]
        self.assertIn("🇩🇪 Deutschland", labels)
        self.assertIn("🇦🇹 Österreich", labels)
        self.assertIn("🇮🇹 Italien", labels)
        self.assertNotIn("Германия", " ".join(labels))

    def test_german_timezone_and_currency_screens_are_localized(self):
        timezone_labels = [row[0].text for row in timezone_keyboard_for("de").inline_keyboard]
        self.assertTrue(any("Warschau" in label for label in timezone_labels))
        self.assertTrue(any("Wien" in label for label in timezone_labels))
        self.assertEqual(timezone_labels[-1], t("de", "nav.back"))
        currency = currency_keyboard_for("de")
        self.assertEqual(currency.inline_keyboard[-1][0].text, t("de", "nav.back"))
        self.assertIn("EUR (€)", [row[0].text for row in currency.inline_keyboard[:-1]])

    def test_settings_summary_localizes_country_and_timezone_only_for_display(self):
        data = {"language":"de", "currency":"EUR", "country":"DE", "city":"Berlin",
                "timezone":"Europe/Berlin", "temporary_screen_ttl":20}
        text = family_settings_text(data)
        self.assertIn("Deutschland", text)
        self.assertIn("Berlin", text)
        self.assertNotIn("Германия", text)
        self.assertEqual(country_name("uk", "DE"), "Німеччина")
        self.assertEqual(timezone_name("de", "Europe/Warsaw"), "Warschau")
        self.assertEqual(data["country"], "DE")
        self.assertEqual(data["timezone"], "Europe/Berlin")

    def test_settings_callback_data_is_language_independent(self):
        for builder in (country_keyboard,):
            de = [[b.callback_data for b in row] for row in builder(0, "de").inline_keyboard]
            uk = [[b.callback_data for b in row] for row in builder(0, "uk").inline_keyboard]
            self.assertEqual(de, uk)
        de = [[b.callback_data for b in row] for row in timezone_keyboard_for("de").inline_keyboard]
        en = [[b.callback_data for b in row] for row in timezone_keyboard_for("en").inline_keyboard]
        self.assertEqual(de, en)

    def test_labels_exist_for_all_supported_locales(self):
        for language in ("ru", "uk", "de", "en", "be", "pl", "cs", "sk", "ro", "bg", "hu"):
            self.assertTrue(country_name(language, "DE"))
            self.assertTrue(timezone_name(language, "Europe/Vienna"))


class SavingsGoalNavigationRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_edit_field_prompts_include_stable_cancel_callback(self):
        goal = SimpleNamespace(id=9, target_amount=10000, deadline=None)
        snapshot = SimpleNamespace(goal=goal)
        for action in ("edit_name", "edit_amount"):
            with self.subTest(action=action):
                message = SimpleNamespace(edit_text=AsyncMock())
                callback = SimpleNamespace(message=message, from_user=SimpleNamespace(id=123), answer=AsyncMock())
                state = SimpleNamespace(clear=AsyncMock(), update_data=AsyncMock(), set_state=AsyncMock())
                family = SimpleNamespace(id=7, currency="EUR")
                with patch.object(savings_goal, "_context", AsyncMock(return_value=(message, family, "de"))), \
                     patch.object(savings_goal, "get_goal_snapshot", AsyncMock(return_value=snapshot)):
                    await savings_goal.goal_callback(callback, GoalCallback(action=action, goal_id=9), state)
                markup = message.edit_text.await_args.kwargs["reply_markup"]
                cancel = GoalCallback.unpack(markup.inline_keyboard[0][0].callback_data)
                self.assertEqual((cancel.action, cancel.goal_id), ("edit", 9))
                self.assertEqual(markup.inline_keyboard[0][0].text, t("de", "goal.cancel"))

    async def test_cancel_clears_state_and_returns_to_edit_without_update(self):
        message = SimpleNamespace(edit_text=AsyncMock())
        callback = SimpleNamespace(message=message, from_user=SimpleNamespace(id=123), answer=AsyncMock())
        state = SimpleNamespace(clear=AsyncMock())
        family = SimpleNamespace(id=7)
        with patch.object(savings_goal, "_context", AsyncMock(return_value=(message, family, "uk"))), \
             patch.object(savings_goal, "_show_edit", AsyncMock(return_value=True)) as show_edit, \
             patch.object(savings_goal, "update_goal_name", AsyncMock()) as update_name:
            await savings_goal.goal_callback(callback, GoalCallback(action="edit", goal_id=9), state)
        state.clear.assert_awaited_once()
        show_edit.assert_awaited_once_with(message, family, "uk", 9)
        update_name.assert_not_awaited()

    async def test_deadline_input_has_cancel_to_edit_screen(self):
        message = SimpleNamespace(edit_text=AsyncMock())
        callback = SimpleNamespace(message=message, from_user=SimpleNamespace(id=123), answer=AsyncMock())
        state = SimpleNamespace(clear=AsyncMock(), update_data=AsyncMock(), set_state=AsyncMock())
        family = SimpleNamespace(id=7)
        with patch.object(savings_goal, "_context", AsyncMock(return_value=(message, family, "en"))):
            await savings_goal.goal_callback(
                callback, GoalCallback(action="enter_edit_deadline", goal_id=9), state,
            )
        markup = message.edit_text.await_args.kwargs["reply_markup"]
        cancel = GoalCallback.unpack(markup.inline_keyboard[0][0].callback_data)
        self.assertEqual((cancel.action, cancel.goal_id), ("edit", 9))
        self.assertEqual(markup.inline_keyboard[0][0].text, t("en", "goal.cancel"))

    async def test_goal_back_returns_localized_family_settings(self):
        message = SimpleNamespace(edit_text=AsyncMock())
        callback = SimpleNamespace(message=message, from_user=SimpleNamespace(id=123), answer=AsyncMock())
        state = SimpleNamespace(clear=AsyncMock())
        family = SimpleNamespace(id=7)
        data = {"language":"de", "currency":"EUR", "country":"DE", "city":"Berlin",
                "timezone":"Europe/Berlin", "temporary_screen_ttl":20}
        with patch.object(savings_goal, "_context", AsyncMock(return_value=(message, family, "de"))), \
             patch("app.services.settings_service.get_current_family_settings", AsyncMock(return_value=data)):
            await savings_goal.goal_callback(callback, GoalCallback(action="back", goal_id=0), state)
        state.clear.assert_awaited_once()
        text = message.edit_text.await_args.args[0]
        self.assertIn(t("de", "settings.title"), text)
        self.assertIn("Deutschland", text)

    def test_deadline_and_project_edit_cancel_are_localized(self):
        for language in ("de", "uk", "en"):
            goal_cancel = goal_edit_cancel_keyboard(9, language).inline_keyboard[0][0]
            self.assertEqual(goal_cancel.text, t(language, "goal.cancel"))
            self.assertEqual(GoalCallback.unpack(goal_cancel.callback_data).action, "edit")
            project_cancel = project_cancel_keyboard(language).inline_keyboard[0][0]
            self.assertEqual(project_cancel.text, t(language, "projects.cancel"))

    def test_project_card_system_labels_are_localized_but_user_data_is_not(self):
        project = SimpleNamespace(name="Ремонт", tag="дом", is_active=True)
        text = project_card_text(project, 100, 2, "EUR", "de")
        self.assertIn("Ремонт", text)
        self.assertIn("#дом", text)
        self.assertIn("Status: 🟢 Aktiv", text)
        self.assertNotIn("Активен", text)


if __name__ == "__main__":
    unittest.main()
