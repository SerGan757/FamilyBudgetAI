import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.constants import APP_VERSION
from app.handlers import settings
from app.keyboards.main_menu import main_menu
from app.keyboards.settings_menu import family_settings_keyboard, family_settings_keyboard_for_ttl, settings_menu


class Message:
    def __init__(self, text="⚙️ Настройки"):
        self.text = text
        self.from_user = SimpleNamespace(id=1)
        self.chat = SimpleNamespace(id=100, type="private")
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


class SettingsTests(unittest.IsolatedAsyncioTestCase):
    def test_keyboard_layouts(self):
        self.assertEqual([len(row) for row in main_menu.keyboard], [2, 2, 2, 2])
        self.assertEqual(
            [[button.text for button in row] for row in main_menu.keyboard],
            [
                ["📋 История", "📅 Сегодня"],
                ["📅 Месяц", "📈 Год"],
                ["📊 Аналитика", "🗑️ Удалить"],
                ["🔁 Регулярные", "⚙️ Настройки"],
            ],
        )
        self.assertTrue(main_menu.resize_keyboard)
        self.assertTrue(main_menu.one_time_keyboard)
        self.assertIn("📋 История", [button.text for row in main_menu.keyboard for button in row])
        self.assertIn("⚙️ Настройки", [button.text for row in main_menu.keyboard for button in row])
        self.assertEqual([len(row) for row in settings_menu.keyboard], [2, 2, 2, 2])

    async def test_settings_screen_escapes_family_and_opens_menu(self):
        message = Message()
        data = {"id": 3, "name": "<Family>", "language": "uk", "country": None,
                "city": "Berlin", "timezone": "Europe/Berlin", "currency": "EUR",
                "temporary_screen_ttl": 20}
        with patch.object(settings, "get_current_family_settings", AsyncMock(return_value=data)) as get_data:
            await settings.open_settings(message)
        self.assertIn("Українська", message.answers[0][0])
        self.assertIn("Berlin", message.answers[0][0])
        self.assertEqual(
            message.answers[0][1]["reply_markup"],
            family_settings_keyboard_for_ttl(20, "uk"),
        )
        get_data.assert_awaited_once_with(1)

    async def test_members_and_about(self):
        message = Message("👥 Участники")
        family = SimpleNamespace(id=3)
        with patch.object(settings, "require_family_for_chat", AsyncMock(return_value=family)) as require_family, \
             patch.object(settings, "get_family_members", AsyncMock(return_value=[SimpleNamespace(name="<Ann>")])) as get_members:
            await settings.members(message)
        self.assertIn("&lt;Ann&gt;", message.answers[0][0])
        self.assertEqual(message.answers[0][1]["reply_markup"], settings_menu)
        require_family.assert_awaited_once_with(
            100, chat_type="private", telegram_id=1,
        )
        get_members.assert_awaited_once_with(3)

        about = Message("ℹ️ О программе")
        await settings.about(about)
        self.assertIn(APP_VERSION, about.answers[0][0])
