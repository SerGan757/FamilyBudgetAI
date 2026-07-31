import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.constants import APP_VERSION
from app.handlers import settings
from app.keyboards.main_menu import main_menu
from app.keyboards.settings_menu import settings_menu


class Message:
    def __init__(self, text="⚙️ Настройки"):
        self.text = text
        self.from_user = SimpleNamespace(id=1)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


class SettingsTests(unittest.IsolatedAsyncioTestCase):
    def test_keyboard_layouts(self):
        self.assertEqual([len(row) for row in main_menu.keyboard], [2, 2, 2, 2])
        self.assertIn("📋 История", [button.text for row in main_menu.keyboard for button in row])
        self.assertIn("⚙️ Настройки", [button.text for row in main_menu.keyboard for button in row])
        self.assertEqual([len(row) for row in settings_menu.keyboard], [2, 2, 2, 2])

    async def test_settings_screen_escapes_family_and_opens_menu(self):
        message = Message()
        data = {"id": 3, "name": "<Family>", "created_at": datetime(2026, 7, 17),
                "members_count": 5, "transactions_count": 328, "recurring_count": 21}
        with patch.object(settings, "get_family_settings_data", AsyncMock(return_value=data)):
            await settings.open_settings(message)
        self.assertIn("&lt;Family&gt;", message.answers[0][0])
        self.assertEqual(message.answers[0][1]["reply_markup"], settings_menu)

    async def test_members_and_about(self):
        message = Message("👥 Участники")
        with patch.object(settings, "get_family_members", AsyncMock(return_value=[SimpleNamespace(name="<Ann>")])):
            await settings.members(message)
        self.assertIn("&lt;Ann&gt;", message.answers[0][0])
        self.assertEqual(message.answers[0][1]["reply_markup"], settings_menu)

        about = Message("ℹ️ О программе")
        await settings.about(about)
        self.assertIn(APP_VERSION, about.answers[0][0])
