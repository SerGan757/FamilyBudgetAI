import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

from app.handlers import year_analytics
from app.i18n import all_texts, t
from app.i18n.translations import SUPPORTED_LANGUAGES
from app.keyboards.main_menu import main_menu_keyboard
from app.services.year_analytics_service import YearAnalytics, YearMonth, year_bounds


def snapshot(months=(), categories=(), members=(), goals=(), **values):
    return YearAnalytics(
        2026, tuple(months), tuple(categories), tuple(members), tuple(goals),
        values.get("income", sum(row.income for row in months)),
        values.get("expense", sum(row.expense for row in months)),
        values.get("goal_contributions", sum(row.goals for row in months)),
        values.get("recurring_income_load", 0), values.get("recurring_expense_load", 0),
        values.get("recurring_actual_income", 0), values.get("recurring_actual_expense", 0),
    )


class YearCalculationTests(unittest.TestCase):
    def test_empty_year_is_safe(self):
        data=snapshot();self.assertEqual(data.months_with_data,0);self.assertEqual(data.average_income,0);self.assertEqual(data.financial_result,0)

    def test_one_and_two_month_totals_and_average_use_active_months(self):
        one=snapshot([YearMonth(7,1000,400,100)])
        self.assertEqual((one.income,one.expense,one.goal_contributions,one.financial_result),(1000,400,100,500))
        two=snapshot([YearMonth(7,1000,400,100),YearMonth(8,3000,600,200)])
        self.assertEqual(two.months_with_data,2);self.assertEqual(two.average_income,2000);self.assertEqual(two.average_expense,500);self.assertEqual(two.average_goals,150)

    def test_goal_is_subtracted_once_from_cash_balance(self):
        data=snapshot([YearMonth(8,4566,3742.35,500)])
        self.assertAlmostEqual(data.financial_result,323.65);self.assertNotEqual(data.financial_result,4566-3742.35-1000)

    def test_month_highlights(self):
        data=snapshot([YearMonth(7,650,1143.49,500),YearMonth(8,3916,2598.86,0)])
        self.assertEqual(data.best_income_month.month,8);self.assertEqual(data.highest_expense_month.month,8)
        self.assertEqual(data.best_result_month.month,8);self.assertEqual(data.worst_result_month.month,7)

    def test_timezone_year_boundaries(self):
        start,end=year_bounds(2026,"Europe/Berlin")
        self.assertEqual(start,datetime(2025,12,31,23));self.assertEqual(end,datetime(2026,12,31,23))
        fallback=year_bounds(2026,"Invalid/Zone");self.assertEqual(fallback,(start,end))


class YearUiTests(unittest.IsolatedAsyncioTestCase):
    def family(self):return SimpleNamespace(id=7,language="en",timezone="Europe/Berlin",currency="EUR")

    def test_all_locales_have_every_year_key(self):
        keys=("menu.year","year.title","year.period","year.month_count","year.income","year.expense","year.to_goals","year.result","year.average","year.best_income","year.highest_expense","year.best_result","year.worst_result","year.dynamics","year.categories","year.members","year.current_load","year.actual_expense","year.actual_income","year.saved","year.months","year.back")
        for language in SUPPORTED_LANGUAGES:
            for key in keys:self.assertNotEqual(t(language,key,year=2026) if key=="year.title" else t(language,key),key)

    def test_main_menu_replaces_visible_balance_but_old_translation_remains(self):
        labels=[button.text for row in main_menu_keyboard("en").keyboard for button in row]
        self.assertIn(t("en","menu.year"),labels);self.assertNotIn(t("en","menu.balance"),labels)
        self.assertIn(t("en","menu.balance"),all_texts("menu.balance"))

    def test_year_navigation_has_no_future_beyond_current(self):
        keyboard=year_analytics.year_keyboard(2026,2026,"en")
        callbacks=[button.callback_data for row in keyboard.inline_keyboard for button in row]
        self.assertIn("year:main:2025",callbacks);self.assertNotIn("year:main:2027",callbacks)
        old=year_analytics.year_keyboard(2025,2026,"en");self.assertIn("year:main:2026",[b.callback_data for r in old.inline_keyboard for b in r])

    def test_result_icon_follows_value_sign(self):
        self.assertEqual(year_analytics._result_icon(1),"🟢")
        self.assertEqual(year_analytics._result_icon(-1),"🔴")
        self.assertEqual(year_analytics._result_icon(0),"⚪")

    async def test_main_screen_is_compact_and_negative_best_worst_are_red(self):
        data=snapshot(
            [YearMonth(8,2480,1503.64,1100)],
            categories=(("📦 Other",838.98,None),),
        )
        hide_message=SimpleNamespace(delete=AsyncMock())
        year_message=SimpleNamespace(delete=AsyncMock())
        message=SimpleNamespace(answer=AsyncMock(side_effect=[hide_message,year_message]))
        with patch.object(year_analytics,"get_year_analytics",AsyncMock(return_value=data)):
            await year_analytics.render_year(message,self.family(),2026)
        text=message.answer.await_args_list[1].args[0]
        self.assertNotIn("━━━━━━━━",text)
        self.assertNotIn("\n\n\n",text)
        self.assertIn("🔴 <b>Financial result: -123.64 €</b>",text)
        self.assertIn("🔴 Best result: August — -123.64 €",text)
        self.assertIn("🔴 Worst result: August — -123.64 €",text)
        self.assertIn("August\n💰 2 480.00 € | 💸 1 503.64 € | 🔴 -123.64 €",text)

    async def test_year_entry_hides_reply_keyboard_and_keeps_inline_navigation(self):
        hide_message=SimpleNamespace(delete=AsyncMock())
        year_message=SimpleNamespace(delete=AsyncMock())
        message=SimpleNamespace(answer=AsyncMock(side_effect=[hide_message,year_message]))
        with patch.object(year_analytics,"get_year_analytics",AsyncMock(return_value=snapshot())):
            await year_analytics.render_year(message,self.family(),2026)
        self.assertEqual(message.answer.await_count,2)
        self.assertIsInstance(message.answer.await_args_list[0].kwargs["reply_markup"],ReplyKeyboardRemove)
        inline=message.answer.await_args_list[1].kwargs["reply_markup"]
        self.assertIsInstance(inline,InlineKeyboardMarkup)
        callbacks=[[button.callback_data for button in row] for row in inline.inline_keyboard]
        self.assertEqual(callbacks,[
            ["year:months:2026"],
            ["year:categories:2026","year:members:2026"],
            ["year:goals:2026"],
            ["year:charts:2026"],
            ["year:main:2025"],
            ["year:back:0"],
        ])
        hide_message.delete.assert_awaited_once()
        year_message.delete.assert_not_awaited()

    async def test_hide_message_delete_failure_does_not_break_year_screen(self):
        hide_message=SimpleNamespace(delete=AsyncMock(side_effect=RuntimeError("delete failed")))
        year_message=SimpleNamespace(delete=AsyncMock())
        message=SimpleNamespace(answer=AsyncMock(side_effect=[hide_message,year_message]))
        with patch.object(year_analytics,"get_year_analytics",AsyncMock(return_value=snapshot())):
            result=await year_analytics.render_year(message,self.family(),2026)
        self.assertIs(result,year_message)
        self.assertEqual(message.answer.await_count,2)
        self.assertIsInstance(message.answer.await_args_list[1].kwargs["reply_markup"],InlineKeyboardMarkup)
        year_message.delete.assert_not_awaited()

    def test_old_year_layout_includes_next_year_without_dead_end(self):
        keyboard=year_analytics.year_keyboard(2025,2026,"en")
        callbacks=[[button.callback_data for button in row] for row in keyboard.inline_keyboard]
        self.assertEqual(callbacks[-2],["year:main:2024","year:main:2026"])
        self.assertEqual(callbacks[-1],["year:back:0"])

    async def test_year_subscreen_edits_message_without_restoring_main_keyboard(self):
        data=snapshot([YearMonth(8,100,20,0)])
        callback=SimpleNamespace(
            message=SimpleNamespace(chat=SimpleNamespace(id=1,type="private"),edit_text=AsyncMock(),answer=AsyncMock()),
            from_user=SimpleNamespace(id=2),data="year:months:2026",answer=AsyncMock(),
        )
        with patch.object(year_analytics,"_family",AsyncMock(return_value=self.family())),patch.object(year_analytics,"get_year_analytics",AsyncMock(return_value=data)):
            await year_analytics.year_callback(callback)
        callback.message.answer.assert_not_awaited()
        self.assertIsInstance(callback.message.edit_text.await_args.kwargs["reply_markup"],InlineKeyboardMarkup)

    async def test_back_deletes_year_screen_and_restores_main_reply_keyboard(self):
        callback=SimpleNamespace(
            message=SimpleNamespace(chat=SimpleNamespace(id=1,type="private"),delete=AsyncMock(),answer=AsyncMock()),
            from_user=SimpleNamespace(id=2),data="year:back:0",answer=AsyncMock(),
        )
        with patch.object(year_analytics,"_family",AsyncMock(return_value=self.family())):
            await year_analytics.year_callback(callback)
        callback.message.delete.assert_awaited_once()
        markup=callback.message.answer.await_args.kwargs["reply_markup"]
        self.assertIsInstance(markup,ReplyKeyboardMarkup)
        self.assertEqual(markup,main_menu_keyboard("en"))

    async def test_member_zero_expense_and_custom_category_render(self):
        data=snapshot(categories=(("🎬 Entertainment",20,17),),members=(("Anna",0),))
        callback=SimpleNamespace(message=SimpleNamespace(chat=SimpleNamespace(id=1,type="private"),edit_text=AsyncMock()),from_user=SimpleNamespace(id=2),data="year:members:2026",answer=AsyncMock())
        with patch.object(year_analytics,"_family",AsyncMock(return_value=self.family())),patch.object(year_analytics,"get_year_analytics",AsyncMock(return_value=data)):
            await year_analytics.year_callback(callback)
        self.assertIn("0%",callback.message.edit_text.await_args.args[0])

    async def test_callback_uses_current_family_not_callback_family_id(self):
        callback=SimpleNamespace(message=SimpleNamespace(chat=SimpleNamespace(id=1,type="private"),edit_text=AsyncMock()),from_user=SimpleNamespace(id=2),data="year:main:2026",answer=AsyncMock())
        family=self.family()
        with patch.object(year_analytics,"_family",AsyncMock(return_value=family)),patch.object(year_analytics,"get_year_analytics",AsyncMock(return_value=snapshot())) as service:
            await year_analytics.year_callback(callback)
        service.assert_awaited_once_with(7,2026,"Europe/Berlin")

    def test_system_custom_members_goals_and_recurring_contract(self):
        data=snapshot(categories=(("🛒 Продукты",100,None),("🎬 Cinema",50,17)),members=(("A",150),),goals=(("Car",30),),recurring_income_load=200,recurring_expense_load=80,recurring_actual_income=150,recurring_actual_expense=70)
        self.assertEqual(data.categories[0][2],None);self.assertEqual(data.categories[1][2],17)
        self.assertEqual(data.members[0][1],150);self.assertEqual(data.goals[0][1],30)
        self.assertEqual((data.recurring_income_load,data.recurring_expense_load,data.recurring_actual_income,data.recurring_actual_expense),(200,80,150,70))

    def test_custom_category_name_is_not_translated(self):
        self.assertEqual(year_analytics._category_display("de","🎬 Развлечения",17),"🎬 Развлечения")

    def test_service_is_family_scoped_and_uses_grouping(self):
        import inspect
        source=inspect.getsource(__import__("app.services.year_analytics_service",fromlist=["get_year_analytics"]).get_year_analytics)
        self.assertGreaterEqual(source.count("family_id == family_id"),7)
        self.assertIn("group_by",source);self.assertNotIn("for month in range",source)


if __name__ == "__main__": unittest.main()
