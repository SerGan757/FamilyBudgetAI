import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app import constants
from app.handlers import settings
from app.keyboards.settings_menu import FamilySettingsCallback, family_settings_keyboard


SETTINGS_DATA = {
    "id": 1, "name": "Family", "language": "ru", "country": "DE",
    "city": "Berlin", "timezone": "Europe/Berlin", "currency": "EUR",
}


class AppMetadataTests(unittest.TestCase):
    def test_centralized_public_metadata(self):
        self.assertEqual(constants.APP_NAME, "FamilyBudgetAI")
        self.assertEqual(constants.APP_VERSION, "2.0")
        self.assertEqual(constants.DEVELOPER_NAME, "SerGan")
        self.assertEqual(constants.DEVELOPER_TELEGRAM, "@sergan757")

class AboutScreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_about_is_visible_and_back_returns_to_settings(self):
        button_texts = [
            button.text for row in family_settings_keyboard.inline_keyboard for button in row
        ]
        self.assertIn("ℹ️ О боте", button_texts)

        message = SimpleNamespace(edit_text=AsyncMock())
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=123), message=message, answer=AsyncMock(),
        )
        state = SimpleNamespace(clear=AsyncMock())
        with patch.object(
            settings, "get_current_family_settings", AsyncMock(return_value=SETTINGS_DATA),
        ):
            await settings.family_settings_callback(
                callback, FamilySettingsCallback(action="about", value=""), state,
            )

        text = message.edit_text.await_args.args[0]
        self.assertIn("FamilyBudgetAI", text)
        self.assertIn("Версия: 2.0", text)
        self.assertIn("SerGan", text)
        self.assertIn("@sergan757", text)
        self.assertIn("Работает прямо в семейном чате", text)
        self.assertIn("<code>кофе 3.50</code>", text)
        self.assertIn("<code>зарплата +2300</code>", text)
        self.assertIn("<code>++500</code>", text)
        self.assertIn("<code>краска 45 #ремонт</code>", text)
        self.assertIn("Аналитика года", text)
        self.assertIn("Наглядные графики", text)
        self.assertIn("исчезающие сообщения", text)
        self.assertNotIn("====================", text)
        self.assertNotIn("\n\n\n", text)
        self.assertIn("✈️ Telegram: @sergan757", text)
        self.assertNotIn("<a href=", text)
        self.assertNotIn("https://t.me/", text)
        for secret in (
            "DATABASE_URL", "BOT_TOKEN", "ADMIN_TELEGRAM_IDS", "postgresql://",
            "3d7ad24d92b7f96166d3c43f175037be3c656fef",
        ):
            self.assertNotIn(secret, text)

        keyboard = message.edit_text.await_args.kwargs["reply_markup"]
        packed = keyboard.inline_keyboard[0][0].callback_data
        self.assertEqual(FamilySettingsCallback.unpack(packed).action, "home")

    def test_about_uses_family_currency_symbol(self):
        text = settings.about_text("en", "PLN")
        self.assertIn("500 zł", text)
        self.assertNotIn("500 €", text)


if __name__ == "__main__":
    unittest.main()
