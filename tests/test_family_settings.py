import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers import settings
from app.handlers.settings_states import FamilySettingsState
from app.keyboards.settings_menu import (
    FamilySettingsCallback, country_keyboard, currency_keyboard, family_settings_keyboard,
    language_keyboard, temporary_screen_ttl_keyboard,
)
from app.services import settings_service
from app.services.country_catalog import COUNTRIES, COUNTRIES_BY_CODE


DATA = {
    "id": 7, "name": "Family", "language": "ru", "country": "DE",
    "city": "Berlin", "timezone": "Europe/Berlin", "currency": "EUR",
    "temporary_screen_ttl": 20,
}


class FakeMessage:
    def __init__(self, text=""):
        self.text = text
        self.from_user = SimpleNamespace(id=123)
        self.chat = SimpleNamespace(id=456, type="private")
        self.answers = []
        self.edits = []
        self.deleted = False

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))

    async def edit_text(self, text, **kwargs):
        self.edits.append((text, kwargs))

    async def delete(self):
        self.deleted = True


class FakeCallback:
    def __init__(self):
        self.from_user = SimpleNamespace(id=123)
        self.message = FakeMessage()
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))


class FakeState:
    def __init__(self):
        self.value = None
        self.cleared = 0

    async def set_state(self, value):
        self.value = value

    async def clear(self):
        self.value = None
        self.cleared += 1


class FamilySettingsValidationTests(unittest.TestCase):
    def test_all_supported_languages_timezones_and_currencies(self):
        for value in ("ru", "uk", "de", "en", "be"):
            self.assertEqual(settings_service.validate_family_setting("language", value), value)
        for value in settings_service.TIMEZONE_VALUES:
            self.assertEqual(settings_service.validate_family_setting("timezone", value), value)
        for value in settings_service.CURRENCY_CODES:
            self.assertEqual(settings_service.validate_family_setting("currency", value), value)
        for field, value in (("language", "fr"), ("timezone", "Moon/Base"), ("currency", "BTC")):
            with self.assertRaises(ValueError):
                settings_service.validate_family_setting(field, value)
        self.assertEqual(
            settings_service.CURRENCY_CODES,
            {"EUR", "USD", "UAH", "GBP", "PLN", "CZK", "RON", "CHF", "HUF", "SEK", "NOK", "DKK"},
        )
        self.assertEqual(
            settings_service.TIMEZONE_VALUES,
            {country.timezone for country in COUNTRIES} | {"UTC"},
        )

    def test_city_validation_and_country_is_not_free_text(self):
        self.assertEqual(settings_service.validate_family_setting("city", "Berlin"), "Berlin")
        for field, value in (("country", "DE"), ("city", "   "), ("city", "/start")):
            with self.assertRaises(ValueError):
                settings_service.validate_family_setting(field, value)

    def test_callback_contains_no_family_id(self):
        packed = FamilySettingsCallback(action="set_language", value="uk").pack()
        self.assertNotIn("family", packed)
        self.assertNotIn("7", packed)

    def test_screen_contains_all_fields(self):
        text = settings.family_settings_text(DATA)
        for value in ("Русский", "🌍 Страна: 🇩🇪 Германия", "🏙 Город: Berlin", "Europe/Berlin", "EUR (€)"):
            self.assertIn(value, text)

    def test_language_list_is_exact_and_belarusian_is_human_readable(self):
        self.assertEqual(settings_service.LANGUAGE_CODES, {"ru", "uk", "de", "en", "be"})
        self.assertIn("Беларуская", settings.family_settings_text({**DATA, "language": "be"}))
        language_buttons = [row[0] for row in language_keyboard.inline_keyboard[:-1]]
        self.assertEqual(
            [button.text for button in language_buttons],
            ["🇷🇺 Русский", "🇺🇦 Українська", "🇩🇪 Deutsch", "🇬🇧 English", "🇧🇾 Беларуская"],
        )

    def test_null_country_and_city_are_displayed_separately(self):
        text = settings.family_settings_text({**DATA, "country": None, "city": None})
        self.assertIn("🌍 Страна: —", text)
        self.assertIn("🏙 Город: —", text)

    def test_all_currencies_have_symmetric_display(self):
        expected = {
            "EUR": "EUR (€)", "USD": "USD ($)", "UAH": "UAH (₴)",
            "GBP": "GBP (£)", "PLN": "PLN (zł)", "CZK": "CZK (Kč)",
            "RON": "RON (lei)", "CHF": "CHF (CHF)", "HUF": "HUF (Ft)",
            "SEK": "SEK (kr)", "NOK": "NOK (kr)", "DKK": "DKK (kr)",
        }
        for code, label in expected.items():
            self.assertIn(label, settings.family_settings_text({**DATA, "currency": code}))
        self.assertEqual(
            [row[0].text for row in currency_keyboard.inline_keyboard[:-1]],
            list(expected.values()),
        )

    def test_country_catalog_and_pagination(self):
        self.assertEqual(len(COUNTRIES), 20)
        self.assertEqual(len(COUNTRIES_BY_CODE), 20)
        self.assertEqual([len(country.code) for country in COUNTRIES], [2] * 20)
        first = country_keyboard(0)
        second = country_keyboard(1)
        self.assertEqual(len(first.inline_keyboard[:10]), 10)
        self.assertEqual(len(second.inline_keyboard[:10]), 10)
        packed = first.inline_keyboard[0][0].callback_data
        self.assertNotIn("family", packed)
        self.assertEqual(
            [(item.code, item.currency, item.timezone) for item in COUNTRIES],
            [
                ("DE", "EUR", "Europe/Berlin"), ("AT", "EUR", "Europe/Vienna"),
                ("IT", "EUR", "Europe/Rome"), ("ES", "EUR", "Europe/Madrid"),
                ("FR", "EUR", "Europe/Paris"), ("NL", "EUR", "Europe/Amsterdam"),
                ("BE", "EUR", "Europe/Brussels"), ("SK", "EUR", "Europe/Bratislava"),
                ("PT", "EUR", "Europe/Lisbon"), ("UA", "UAH", "Europe/Kyiv"),
                ("PL", "PLN", "Europe/Warsaw"), ("CZ", "CZK", "Europe/Prague"),
                ("RO", "RON", "Europe/Bucharest"), ("BG", "EUR", "Europe/Sofia"),
                ("GB", "GBP", "Europe/London"), ("CH", "CHF", "Europe/Zurich"),
                ("HU", "HUF", "Europe/Budapest"), ("SE", "SEK", "Europe/Stockholm"),
                ("NO", "NOK", "Europe/Oslo"), ("DK", "DKK", "Europe/Copenhagen"),
            ],
        )

    def test_legacy_country_value_is_safe(self):
        text = settings.family_settings_text({**DATA, "country": "Germany legacy"})
        self.assertIn("🌍 Страна: Germany legacy", text)


class FamilySettingsHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_view_uses_current_telegram_user_and_does_not_touch(self):
        message = FakeMessage("⚙️ Настройки")
        with patch.object(settings, "get_current_family_settings", AsyncMock(return_value=DATA)) as get_data, \
             patch.object(settings, "update_current_family_setting", AsyncMock()) as update:
            await settings.open_settings(message)
        get_data.assert_awaited_once_with(123)
        update.assert_not_awaited()
        self.assertEqual(message.answers[0][1]["reply_markup"], family_settings_keyboard)

    async def test_select_update_uses_telegram_id_not_family_id(self):
        callback, state = FakeCallback(), FakeState()
        with patch.object(settings, "get_current_family_settings", AsyncMock(return_value=DATA)), \
             patch.object(settings, "update_current_family_setting", AsyncMock(return_value=True)) as update:
            await settings.family_settings_callback(
                callback, FamilySettingsCallback(action="set_language", value="uk"), state,
            )
        update.assert_awaited_once_with(123, "language", "uk")

    async def test_belarusian_is_saved_as_code(self):
        callback, state = FakeCallback(), FakeState()
        data = {**DATA, "language": "be"}
        with patch.object(settings, "get_current_family_settings", AsyncMock(return_value=data)), \
             patch.object(settings, "update_current_family_setting", AsyncMock(return_value=True)) as update:
            await settings.family_settings_callback(
                callback, FamilySettingsCallback(action="set_language", value="be"), state,
            )
        update.assert_awaited_once_with(123, "language", "be")

    async def test_invalid_callback_value_is_rejected(self):
        callback, state = FakeCallback(), FakeState()
        with patch.object(settings, "get_current_family_settings", AsyncMock(return_value=DATA)), \
             patch.object(settings, "update_current_family_setting", AsyncMock()) as update:
            await settings.family_settings_callback(
                callback, FamilySettingsCallback(action="set_currency", value="BTC"), state,
            )
        update.assert_not_awaited()
        self.assertTrue(callback.answers[-1][1]["show_alert"])

    async def test_country_opens_inline_list_without_fsm(self):
        callback, state = FakeCallback(), FakeState()
        with patch.object(settings, "get_current_family_settings", AsyncMock(return_value=DATA)):
            await settings.family_settings_callback(
                callback, FamilySettingsCallback(action="country", value=""), state,
            )
        self.assertIsNone(state.value)
        self.assertEqual(callback.message.edits[-1][0], "🌍 Выберите страну:")

    async def test_country_selection_uses_iso_and_does_not_change_language_directly(self):
        callback, state = FakeCallback(), FakeState()
        updated_data = {**DATA, "country": "PL", "currency": "PLN", "timezone": "Europe/Warsaw"}
        get_data = AsyncMock(side_effect=[DATA, updated_data, updated_data])
        with patch.object(settings, "get_current_family_settings", get_data), \
             patch.object(settings, "update_current_family_country", AsyncMock(return_value=True)) as update, \
             patch.object(settings, "update_current_family_setting", AsyncMock()) as single_update:
            await settings.family_settings_callback(
                callback, FamilySettingsCallback(action="set_country", value="PL"), state,
            )
        update.assert_awaited_once_with(123, "PL")
        single_update.assert_not_awaited()
        self.assertEqual(updated_data["language"], "ru")

    async def test_unknown_country_callback_is_rejected(self):
        callback, state = FakeCallback(), FakeState()
        with patch.object(settings, "get_current_family_settings", AsyncMock(return_value=DATA)), \
             patch.object(settings, "update_current_family_country", AsyncMock(side_effect=ValueError)):
            await settings.family_settings_callback(
                callback, FamilySettingsCallback(action="set_country", value="XX"), state,
            )
        self.assertTrue(callback.answers[-1][1]["show_alert"])

    async def test_empty_city_keeps_state(self):
        message, state = FakeMessage("   "), FakeState()
        state.value = FamilySettingsState.waiting_for_city
        with patch.object(settings, "update_current_family_setting", AsyncMock()) as update:
            await settings.save_city(message, state)
        update.assert_not_awaited()
        self.assertEqual(state.cleared, 0)

    async def test_city_fsm_success_clears_state(self):
        message, state = FakeMessage(" Prague "), FakeState()
        state.value = FamilySettingsState.waiting_for_city
        city_data = {**DATA, "city": "Prague"}
        with patch.object(settings, "update_current_family_setting", AsyncMock(return_value=True)) as update, \
             patch.object(settings, "get_current_family_settings", AsyncMock(return_value=city_data)):
            await settings.save_city(message, state)
        update.assert_awaited_once_with(123, "city", "Prague")
        self.assertEqual(state.cleared, 1)

    async def test_cancel_clears_state(self):
        callback, state = FakeCallback(), FakeState()
        state.value = FamilySettingsState.waiting_for_city
        with patch.object(settings, "get_current_family_settings", AsyncMock(return_value=DATA)):
            await settings.family_settings_callback(
                callback, FamilySettingsCallback(action="cancel", value=""), state,
            )
        self.assertEqual(state.cleared, 1)

    async def test_temporary_ttl_selection_is_saved_for_resolved_family(self):
        callback, state = FakeCallback(), FakeState()
        updated = {**DATA, "temporary_screen_ttl": 10}
        get_data = AsyncMock(side_effect=[DATA, updated])
        family = SimpleNamespace(id=7, temporary_screen_ttl=20)
        with patch.object(settings, "get_current_family_settings", get_data), \
             patch.object(settings, "require_family_for_chat", AsyncMock(return_value=family)) as context, \
             patch.object(settings, "update_family_temporary_screen_ttl", AsyncMock(return_value=True)) as update:
            await settings.family_settings_callback(
                callback, FamilySettingsCallback(action="set_temporary_ttl", value="10"), state,
            )
        context.assert_awaited_once_with(456, chat_type="private", telegram_id=123)
        update.assert_awaited_once_with(7, 10)
        self.assertIn("10 сек.", callback.message.edits[-1][1]["reply_markup"].inline_keyboard[5][0].text)

    async def test_temporary_ttl_picker_marks_current_value(self):
        callback, state = FakeCallback(), FakeState()
        with patch.object(settings, "get_current_family_settings", AsyncMock(return_value=DATA)):
            await settings.family_settings_callback(
                callback, FamilySettingsCallback(action="temporary_ttl", value=""), state,
            )
        markup = callback.message.edits[-1][1]["reply_markup"]
        self.assertEqual(
            [row[0].text for row in markup.inline_keyboard],
            [row[0].text for row in temporary_screen_ttl_keyboard(20).inline_keyboard],
        )
        self.assertIn("● 20 сек.", [row[0].text for row in markup.inline_keyboard])


class FakeResult:
    def __init__(self, family):
        self.family = family

    def scalar_one_or_none(self):
        return self.family


class FakeSession:
    def __init__(self, family):
        self.family = family
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, _statement):
        return FakeResult(self.family)

    async def commit(self):
        self.committed = True


class FamilySettingsServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_update_touches_family(self):
        for field, value in (("language", "uk"), ("city", "Berlin"),
                             ("timezone", "UTC"), ("currency", "USD")):
            family = SimpleNamespace(id=7)
            session = FakeSession(family)
            with patch.object(settings_service, "SessionLocal", return_value=session), \
                 patch.object(settings_service, "touch_family_activity", AsyncMock()) as touch:
                result = await settings_service.update_current_family_setting(123, field, value)
            self.assertTrue(result)
            self.assertEqual(getattr(family, field), value)
            touch.assert_awaited_once_with(7, session=session)
            self.assertTrue(session.committed)

    async def test_unknown_field_cannot_be_updated(self):
        with self.assertRaises(ValueError):
            await settings_service.update_current_family_setting(123, "plan", "paid")

    async def test_temporary_ttl_update_is_family_scoped_and_persistent(self):
        for ttl in (0, 5, 10, 20, 30, 60):
            family = SimpleNamespace(id=7, temporary_screen_ttl=20)
            session = FakeSession(family)
            session.get = AsyncMock(return_value=family)
            with patch.object(settings_service, "SessionLocal", return_value=session), \
                 patch.object(settings_service, "touch_family_activity", AsyncMock()) as touch:
                result = await settings_service.update_family_temporary_screen_ttl(7, ttl)
            self.assertTrue(result)
            self.assertEqual(family.temporary_screen_ttl, ttl)
            touch.assert_awaited_once_with(7, session=session)
            self.assertTrue(session.committed)

    async def test_invalid_temporary_ttl_is_rejected(self):
        with patch.object(settings_service, "SessionLocal") as session_local:
            with self.assertRaises(ValueError):
                await settings_service.update_family_temporary_screen_ttl(7, 15)
        session_local.assert_not_called()

    async def test_different_families_keep_independent_ttl_values(self):
        families = {
            7: SimpleNamespace(id=7, temporary_screen_ttl=20),
            8: SimpleNamespace(id=8, temporary_screen_ttl=20),
        }
        sessions = []

        def session_factory():
            session = FakeSession(None)
            session.get = AsyncMock(side_effect=lambda _model, family_id: families.get(family_id))
            sessions.append(session)
            return session

        with patch.object(settings_service, "SessionLocal", side_effect=session_factory), \
             patch.object(settings_service, "touch_family_activity", AsyncMock()):
            await settings_service.update_family_temporary_screen_ttl(7, 5)
            await settings_service.update_family_temporary_screen_ttl(8, 60)
        self.assertEqual(families[7].temporary_screen_ttl, 5)
        self.assertEqual(families[8].temporary_screen_ttl, 60)

    async def test_private_and_group_context_update_the_same_family(self):
        family = SimpleNamespace(id=7, temporary_screen_ttl=20)
        for chat_type, chat_id in (("private", 123), ("group", -456)):
            callback, state = FakeCallback(), FakeState()
            callback.message.chat = SimpleNamespace(id=chat_id, type=chat_type)
            with patch.object(settings, "get_current_family_settings", AsyncMock(return_value=DATA)), \
                 patch.object(settings, "require_family_for_chat", AsyncMock(return_value=family)) as context, \
                 patch.object(settings, "update_family_temporary_screen_ttl", AsyncMock(return_value=True)) as update, \
                 patch.object(settings, "_show_current_settings", AsyncMock()):
                await settings.family_settings_callback(
                    callback, FamilySettingsCallback(action="set_temporary_ttl", value="30"), state,
                )
            context.assert_awaited_once_with(
                chat_id, chat_type=chat_type, telegram_id=123,
            )
            update.assert_awaited_once_with(7, 30)

    async def test_country_update_is_atomic_and_touches_once(self):
        expected = {
            "DE": ("EUR", "Europe/Berlin"), "PL": ("PLN", "Europe/Warsaw"),
            "CZ": ("CZK", "Europe/Prague"), "RO": ("RON", "Europe/Bucharest"),
            "BG": ("EUR", "Europe/Sofia"), "CH": ("CHF", "Europe/Zurich"),
        }
        for code, (currency, timezone) in expected.items():
            family = SimpleNamespace(id=7, language="be")
            session = FakeSession(family)
            with patch.object(settings_service, "SessionLocal", return_value=session), \
                 patch.object(settings_service, "touch_family_activity", AsyncMock()) as touch:
                result = await settings_service.update_current_family_country(123, code)
            self.assertTrue(result)
            self.assertEqual((family.country, family.currency, family.timezone), (code, currency, timezone))
            self.assertEqual(family.language, "be")
            touch.assert_awaited_once_with(7, session=session)
            self.assertTrue(session.committed)

    async def test_unknown_country_is_rejected_before_database_access(self):
        with patch.object(settings_service, "SessionLocal") as session_local:
            with self.assertRaises(ValueError):
                await settings_service.update_current_family_country(123, "XX")
        session_local.assert_not_called()

    async def test_manual_overrides_work_and_country_reselection_restores_defaults(self):
        family = SimpleNamespace(id=7, language="uk")
        sessions = []

        def session_factory():
            session = FakeSession(family)
            sessions.append(session)
            return session

        with patch.object(settings_service, "SessionLocal", side_effect=session_factory), \
             patch.object(settings_service, "touch_family_activity", AsyncMock()):
            await settings_service.update_current_family_country(123, "PL")
            await settings_service.update_current_family_setting(123, "currency", "USD")
            await settings_service.update_current_family_setting(123, "timezone", "UTC")
            self.assertEqual((family.country, family.currency, family.timezone), ("PL", "USD", "UTC"))
            await settings_service.update_current_family_country(123, "PL")
        self.assertEqual((family.country, family.currency, family.timezone), ("PL", "PLN", "Europe/Warsaw"))
        self.assertEqual(family.language, "uk")
        self.assertTrue(all(session.committed for session in sessions))
