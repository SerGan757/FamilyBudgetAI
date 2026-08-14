import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers import projects, savings_goal, start
from app.handlers.user_states import RegistrationState
from app.i18n import t
from app.i18n.translations import SUPPORTED_LANGUAGES
from app.services.savings_goal_service import GoalSnapshot


class OnboardingTranslationTests(unittest.TestCase):
    def test_all_locales_have_real_onboarding_texts(self):
        for language in SUPPORTED_LANGUAGES:
            with self.subTest(language=language):
                about = t(language, "onboarding.about", currency="€")
                goal = t(
                    language, "onboarding.goal",
                    target="10 000.00 €", contribution="500.00 €", remaining="9 500.00 €",
                )
                project = t(language, "onboarding.projects")
                self.assertNotEqual(about, "onboarding.about")
                self.assertIn("<code>++500</code>", about)
                self.assertIn("<code>++500</code>", goal)
                self.assertIn("#", project)
                self.assertNotIn("\n\n\n", about + goal + project)

    def test_start_keys_exist_for_every_locale(self):
        for language in SUPPORTED_LANGUAGES:
            with self.subTest(language=language):
                self.assertNotEqual(t(language, "start.welcome"), "start.welcome")
                self.assertIn("Alex", t(language, "start.returning", name="Alex"))
                self.assertNotEqual(t(language, "start.ask_name"), "start.ask_name")
                self.assertIn("Alex", t(language, "start.registered", name="Alex"))

    def test_goal_help_explains_transfer_not_income_or_expense(self):
        text = savings_goal.goal_help_text("PLN", "en")
        self.assertIn("500.00 zł", text)
        self.assertIn("moves", text)
        self.assertIn("neither an expense nor income", text)
        self.assertIn("total money does not change", text)


class OnboardingMainScreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_goal_main_screen_keeps_help_and_create_button(self):
        message = SimpleNamespace(edit_text=AsyncMock())
        family = SimpleNamespace(id=7, currency="EUR")
        with patch.object(savings_goal, "get_goal_snapshot", AsyncMock(return_value=None)):
            await savings_goal._show(message, family, "en")
        text = message.edit_text.await_args.args[0]
        markup = message.edit_text.await_args.kwargs["reply_markup"]
        self.assertIn("<code>++500</code>", text)
        self.assertTrue(any("Create" in button.text for row in markup.inline_keyboard for button in row))

    async def test_active_goal_main_screen_keeps_help_and_goal_buttons(self):
        goal = SimpleNamespace(id=9, name="Car", target_amount=10000, deadline=None)
        snapshot = GoalSnapshot(goal=goal, saved=500, remaining=9500, percentage=5)
        message = SimpleNamespace(edit_text=AsyncMock())
        family = SimpleNamespace(id=7, currency="EUR")
        with patch.object(savings_goal, "get_goal_snapshot", AsyncMock(return_value=snapshot)):
            await savings_goal._show(message, family, "en")
        text = message.edit_text.await_args.args[0]
        markup = message.edit_text.await_args.kwargs["reply_markup"]
        self.assertIn("<code>++500</code>", text)
        self.assertTrue(any("Edit" in button.text for row in markup.inline_keyboard for button in row))

    async def test_active_projects_main_screen_keeps_help_and_buttons(self):
        project = SimpleNamespace(id=3, name="Home", tag="home")
        message = SimpleNamespace(edit_text=AsyncMock())
        settings = {"language": "en", "currency": "EUR"}
        with patch.object(projects, "get_current_family_settings", AsyncMock(return_value=settings)), \
             patch.object(projects, "list_projects", AsyncMock(return_value=([project], 1))):
            await projects._show_projects(message, 123, active=True)
        text = message.edit_text.await_args.args[0]
        markup = message.edit_text.await_args.kwargs["reply_markup"]
        self.assertIn("<code>paint 45 #renovation</code>", text)
        self.assertIn("ordinary budget expense", text)
        self.assertTrue(any(button.text for row in markup.inline_keyboard for button in row))

    async def test_archive_does_not_repeat_main_help(self):
        message = SimpleNamespace(edit_text=AsyncMock())
        settings = {"language": "en", "currency": "EUR"}
        with patch.object(projects, "get_current_family_settings", AsyncMock(return_value=settings)), \
             patch.object(projects, "list_projects", AsyncMock(return_value=([], 0))):
            await projects._show_projects(message, 123, active=False)
        self.assertNotIn("<code>#renovation</code>", message.edit_text.await_args.args[0])


class ActualStartFlowTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _message(language_code="ru-RU"):
        return SimpleNamespace(
            text="/start",
            chat=SimpleNamespace(id=100, title="Family", type="group"),
            from_user=SimpleNamespace(
                id=1, full_name="Vasya", language_code=language_code,
            ),
            answer=AsyncMock(),
        )

    @staticmethod
    def _state():
        return SimpleNamespace(
            clear=AsyncMock(), set_state=AsyncMock(), update_data=AsyncMock(),
        )

    def assert_compact_welcome(self, text):
        for expected in (
            "<code>кофе 3.50</code>", "<code>+150 возврат</code>",
            "<code>++500</code>", "#ремонт", "Аналитика года",
            "Наглядные графики", "проект", "цел", "категор",
            "исчезающие сообщения",
        ):
            self.assertIn(expected.lower(), text.lower())
        self.assertNotIn("<pre>", text)
        self.assertNotIn("====================", text)
        self.assertNotIn("═══", text)
        self.assertNotIn("\n\n\n", text)

    async def test_existing_user_gets_one_actual_welcome_message(self):
        message, state = self._message(), self._state()
        family = SimpleNamespace(id=7, language="ru", currency="PLN")
        user = SimpleNamespace(id=9, family_id=7, name="Вася")
        with patch.object(start, "get_or_create_family_for_chat", AsyncMock(return_value=family)), \
             patch.object(start, "get_user_by_telegram_id", AsyncMock(return_value=user)):
            await start.cmd_start(message, state)
        self.assertEqual(message.answer.await_count, 1)
        text = message.answer.await_args.args[0]
        self.assertTrue(text.startswith("👋 <b>С возвращением, Вася!</b>"))
        self.assertIn("500 zł", text)
        self.assert_compact_welcome(text)
        self.assertIsNotNone(message.answer.await_args.kwargs["reply_markup"])

    async def test_new_user_gets_one_welcome_and_name_prompt(self):
        message, state = self._message(), self._state()
        family = SimpleNamespace(id=7, language="ru", currency="EUR")
        with patch.object(start, "get_or_create_family_for_chat", AsyncMock(return_value=family)), \
             patch.object(start, "get_user_by_telegram_id", AsyncMock(return_value=None)):
            await start.cmd_start(message, state)
        self.assertEqual(message.answer.await_count, 1)
        text = message.answer.await_args.args[0]
        self.assertTrue(text.startswith("👋 <b>Добро пожаловать в Family Budget AI</b>"))
        self.assertIn("Как тебя зовут?", text)
        self.assert_compact_welcome(text)
        state.set_state.assert_awaited_once_with(RegistrationState.waiting_for_name)


if __name__ == "__main__":
    unittest.main()
