import inspect
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.database import init_db as init_db_module
from app.database.models import Family
from app.handlers.admin import family_card_text
from app.services import admin_service, expense_service, recurring_service
from app.services.family_activity_service import touch_family_activity


class FamilyModelTests(unittest.TestCase):
    def test_family_has_subscription_and_locale_fields(self):
        expected = {
            "created_at", "last_activity_at", "country", "city", "language",
            "timezone", "currency", "is_active", "plan", "paid_until",
            "trial_until", "last_payment_at", "disabled_reason",
        }
        self.assertTrue(expected.issubset(Family.__table__.columns.keys()))

    def test_family_defaults(self):
        columns = Family.__table__.c
        self.assertTrue(callable(columns.created_at.default.arg))
        self.assertEqual(columns.language.default.arg, "ru")
        self.assertEqual(columns.timezone.default.arg, "Europe/Berlin")
        self.assertEqual(columns.currency.default.arg, "EUR")
        self.assertEqual(columns.is_active.default.arg, True)
        self.assertEqual(columns.plan.default.arg, "free")

    def test_migration_is_additive_and_backfills_defaults(self):
        source = inspect.getsource(init_db_module.init_db)
        self.assertIn("ADD COLUMN IF NOT EXISTS last_activity_at", source)
        self.assertIn("language = COALESCE(language, 'ru')", source)
        self.assertIn("created_at = COALESCE", source)
        self.assertNotIn("DROP TABLE families", source.upper())


class FamilyCardTests(unittest.TestCase):
    def _family(self, **overrides):
        values = {
            "id": 12, "name": "Семья", "created_at": datetime(2026, 8, 8, 5, 0),
            "last_activity_at": None, "country": None, "city": None,
            "language": "ru", "timezone": "Europe/Berlin", "currency": "EUR",
            "is_active": True, "plan": "free", "paid_until": None,
            "trial_until": None, "last_payment_at": None, "disabled_reason": None,
            "users": 4, "transactions": 847, "recurring_payments": 12,
            "transactions_30_days": 96,
        }
        values.update(overrides)
        return values

    def test_card_shows_metadata_and_missing_values_as_dash(self):
        text = family_card_text(self._family())
        self.assertIn("📅 Создана: 08.08.2026", text)
        self.assertIn("🕐 Последняя активность: —", text)
        self.assertIn("🌍 Страна: —", text)
        self.assertIn("🏙 Город: —", text)
        self.assertIn("💳 Оплачено до: —", text)
        self.assertIn("📊 Операций за 30 дней: 96", text)

    def test_language_codes_are_human_readable(self):
        labels = {"ru": "Русский", "uk": "Українська", "de": "Deutsch", "en": "English"}
        for code, label in labels.items():
            self.assertIn(f"🌐 Язык: {label}", family_card_text(self._family(language=code)))
        self.assertIn("🌐 Язык: custom", family_card_text(self._family(language="custom")))

    def test_active_and_inactive_status_and_reason(self):
        self.assertIn("🟢 Активна", family_card_text(self._family()))
        inactive = family_card_text(self._family(is_active=False, disabled_reason="Пауза"))
        self.assertIn("🔴 Отключена", inactive)
        self.assertIn("Причина: Пауза", inactive)
        self.assertNotIn("Причина:", family_card_text(self._family(disabled_reason="Скрыто")))


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _AdminSession:
    def __init__(self, family):
        self.family = family
        self.values = iter((4, 847, 12, 96))
        self.queries = []

    async def get(self, _model, _identifier):
        return self.family

    async def execute(self, query):
        self.queries.append(query)
        return _ScalarResult(next(self.values))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class _MutationSession:
    def __init__(self, execute_result=None):
        self.execute = AsyncMock(return_value=execute_result)
        self.commit = AsyncMock()
        self.refresh = AsyncMock()

    def add(self, _item):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class ActivityAndStatisticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_transactions_30_days_uses_sql_count(self):
        family = SimpleNamespace(
            id=12, name="Семья", created_at=datetime.now(UTC).replace(tzinfo=None), last_activity_at=None,
            country=None, city=None, language="ru", timezone="Europe/Berlin",
            currency="EUR", is_active=True, plan="free", paid_until=None,
            trial_until=None, last_payment_at=None, disabled_reason=None,
        )
        session = _AdminSession(family)
        with patch.object(admin_service, "SessionLocal", return_value=session):
            result = await admin_service.get_admin_family(12)
        self.assertEqual(result["transactions_30_days"], 96)
        self.assertIn("transactions.created_at >=", str(session.queries[-1]))

    async def test_touch_family_activity_executes_central_update(self):
        session = SimpleNamespace(execute=AsyncMock())
        await touch_family_activity(12, session=session)
        session.execute.assert_awaited_once()
        statement = str(session.execute.await_args.args[0])
        self.assertIn("UPDATE families", statement)
        self.assertIn("last_activity_at", statement)

    async def test_transaction_creation_touches_activity_but_background_recurring_does_not(self):
        session = _MutationSession()
        with patch.object(expense_service, "SessionLocal", return_value=session), \
             patch.object(expense_service, "touch_family_activity", AsyncMock()) as touch:
            await expense_service.create_transaction(1, 12, "Доход", 10, "income")
            touch.assert_awaited_once_with(12, session=session)
            touch.reset_mock()
            await expense_service.create_transaction(
                1, 12, "Шаблон", 10, "expense", is_recurring=True,
            )
            touch.assert_not_awaited()

    async def test_recurring_create_and_update_touch_activity(self):
        payment = SimpleNamespace(id=3, family_id=12)
        result = SimpleNamespace(scalar_one_or_none=lambda: payment)
        session = _MutationSession(result)
        with patch.object(recurring_service, "SessionLocal", return_value=session), \
             patch.object(recurring_service, "touch_family_activity", AsyncMock()) as touch:
            await recurring_service.add_payment(12, "Аренда", 10, "expense", "Дом")
            touch.assert_awaited_with(12, session=session)
            touch.reset_mock()
            await recurring_service.update_payment(3, 12, "Аренда", 11, "expense", "Дом")
            touch.assert_awaited_with(12, session=session)
