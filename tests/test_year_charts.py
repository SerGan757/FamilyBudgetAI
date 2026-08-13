import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from matplotlib import pyplot as plt
import matplotlib

from app.handlers import year_analytics
from app.i18n import category_label, t
from app.i18n.translations import SUPPORTED_LANGUAGES
from app.services.year_analytics_service import YearAnalytics, YearMonth
from app.services.year_chart_service import (
    calendar_series,
    chart_category_label,
    render_categories_chart,
    render_income_expense_chart,
    render_income_sources_chart,
    render_result_chart,
)


PNG_HEADER = b"\x89PNG\r\n\x1a\n"


def snapshot(months=(), categories=(), income_sources=()):
    return YearAnalytics(
        2026,tuple(months),tuple(categories),(),(),
        sum(row.income for row in months),sum(row.expense for row in months),sum(row.goals for row in months),
        0,0,0,0,tuple(income_sources),
    )


def labels():
    return tuple(f"M{month}" for month in range(1,13))


class YearChartRendererTests(unittest.TestCase):
    def test_headless_agg_backend_is_active(self):
        self.assertIn("agg",matplotlib.get_backend().lower())

    def test_income_expense_chart_is_non_empty_png(self):
        png=render_income_expense_chart(snapshot([YearMonth(7,650,1143,0),YearMonth(8,3916,2599,0)]),month_labels=labels(),title="Income / Expense • 2026",income_label="Income",expense_label="Expense",currency="€")
        self.assertTrue(png.startswith(PNG_HEADER));self.assertGreater(len(png),1000)

    def test_income_sources_top_seven_non_empty_png_and_figure_cleanup(self):
        sources=tuple((f"Source {index}",1000-index) for index in range(9))
        before=set(plt.get_fignums())
        png=render_income_sources_chart(sources,title="Income by source • 2026",currency="$")
        self.assertTrue(png.startswith(PNG_HEADER));self.assertGreater(len(png),1000)
        self.assertEqual(set(plt.get_fignums()),before)

    def test_income_sources_empty_is_safe(self):
        self.assertIsNone(render_income_sources_chart((),title="Income",currency="€"))

    def test_result_chart_uses_existing_goal_aware_result(self):
        data=snapshot([YearMonth(8,2480,1503.64,1100)])
        months,income,expense,result=calendar_series(data)
        self.assertEqual(income,(2480,));self.assertEqual(expense,(1503.64,))
        self.assertAlmostEqual(result[0],-123.64)
        png=render_result_chart(data,month_labels=labels(),title="Result • 2026",currency="€")
        self.assertTrue(png.startswith(PNG_HEADER))

    def test_calendar_order_includes_missing_intermediate_month(self):
        data=snapshot([YearMonth(1,10,1,0),YearMonth(3,30,3,0)])
        months,income,expense,result=calendar_series(data)
        self.assertEqual(months,(1,2,3));self.assertEqual(income,(10,None,30))
        self.assertEqual(expense,(1,None,3));self.assertEqual(result,(9,None,27))

    def test_categories_chart_top_seven_custom_and_system_labels(self):
        rows=[(category_label("de","📦 Прочее"),80),("🎬 Kino",70)]+[(f"C{i}",60-i) for i in range(8)]
        png=render_categories_chart(rows,title="Kategorien • 2026",currency="€")
        self.assertTrue(png.startswith(PNG_HEADER))
        self.assertEqual(rows[1][0],"🎬 Kino")
        self.assertEqual(chart_category_label(rows[1][0]),"Kino")

    def test_categories_chart_receives_expense_categories_without_income(self):
        data=snapshot(categories=(("Products",360,None),("Animals",200,17)))
        labels=[label for label,_,_ in data.categories]
        self.assertEqual(labels,["Products","Animals"])
        self.assertNotIn("Income",labels)
        self.assertTrue(render_categories_chart(tuple((label,amount) for label,amount,_ in data.categories),title="Expenses",currency="€").startswith(PNG_HEADER))

    def test_empty_and_zero_category_data_do_not_create_png(self):
        self.assertIsNone(render_income_expense_chart(snapshot(),month_labels=labels(),title="x",income_label="i",expense_label="e",currency="€"))
        self.assertIsNone(render_result_chart(snapshot(),month_labels=labels(),title="x",currency="€"))
        self.assertIsNone(render_categories_chart((("Other",0),),title="x",currency="€"))

    def test_figures_are_closed_after_repeated_rendering(self):
        before=set(plt.get_fignums());data=snapshot([YearMonth(8,100,20,5)])
        for _ in range(3):
            render_result_chart(data,month_labels=labels(),title="Result",currency="EUR")
        self.assertEqual(set(plt.get_fignums()),before)

    def test_all_locales_have_chart_labels(self):
        keys=("year.charts","chart.menu","chart.income_expense","chart.result","chart.categories","chart.insufficient","chart.back_charts","chart.back_year","chart.income","chart.income_sources","chart.total","chart.no_income")
        for language in SUPPORTED_LANGUAGES:
            for key in keys:self.assertNotEqual(t(language,key),key)


class YearChartTelegramTests(unittest.IsolatedAsyncioTestCase):
    def family(self):return SimpleNamespace(id=7,language="en",timezone="Europe/Berlin",currency="USD")

    async def test_chart_callback_uses_family_data_currency_year_and_sends_png(self):
        data=snapshot([YearMonth(8,100,20,5)])
        message=SimpleNamespace(chat=SimpleNamespace(id=1,type="private"),answer_photo=AsyncMock(),delete=AsyncMock())
        callback=SimpleNamespace(message=message,from_user=SimpleNamespace(id=2),data="yearchart:result:2026",answer=AsyncMock())
        with patch.object(year_analytics,"_family",AsyncMock(return_value=self.family())),patch.object(year_analytics,"get_year_analytics",AsyncMock(return_value=data)) as service,patch.object(year_analytics.asyncio,"to_thread",AsyncMock(return_value=PNG_HEADER+b"chart")) as render:
            await year_analytics.year_chart(callback)
        service.assert_awaited_once_with(7,2026,"Europe/Berlin")
        self.assertEqual(render.await_args.kwargs["currency"],"$")
        photo=message.answer_photo.await_args.args[0]
        self.assertTrue(photo.data.startswith(PNG_HEADER));self.assertIn("2026",photo.filename)
        self.assertIn("2026",message.answer_photo.await_args.kwargs["caption"])
        message.delete.assert_awaited_once()

    async def test_category_chart_localizes_system_label_and_preserves_custom_name(self):
        data=snapshot(categories=(("📦 Прочее",80,None),("🎬 Kino",70,17)))
        message=SimpleNamespace(chat=SimpleNamespace(id=1,type="private"),answer_photo=AsyncMock(),delete=AsyncMock())
        callback=SimpleNamespace(message=message,from_user=SimpleNamespace(id=2),data="yearchart:categories:2026",answer=AsyncMock())
        with patch.object(year_analytics,"_family",AsyncMock(return_value=self.family())),patch.object(year_analytics,"get_year_analytics",AsyncMock(return_value=data)),patch.object(year_analytics.asyncio,"to_thread",AsyncMock(return_value=PNG_HEADER+b"chart")) as render:
            await year_analytics.year_chart(callback)
        categories=render.await_args.args[1]
        self.assertEqual(categories[0][0],category_label("en","📦 Прочее"))
        self.assertEqual(categories[1][0],"🎬 Kino")

    async def test_empty_chart_uses_safe_alert_and_sends_no_photo(self):
        message=SimpleNamespace(chat=SimpleNamespace(id=1,type="private"),answer_photo=AsyncMock(),delete=AsyncMock())
        callback=SimpleNamespace(message=message,from_user=SimpleNamespace(id=2),data="yearchart:flow:2026",answer=AsyncMock())
        with patch.object(year_analytics,"_family",AsyncMock(return_value=self.family())),patch.object(year_analytics,"get_year_analytics",AsyncMock(return_value=snapshot())):
            await year_analytics.year_chart(callback)
        message.answer_photo.assert_not_awaited();message.delete.assert_not_awaited()
        self.assertTrue(callback.answer.await_args.kwargs["show_alert"])

    async def test_chart_menu_keeps_inline_navigation_only(self):
        callback=SimpleNamespace(message=SimpleNamespace(chat=SimpleNamespace(id=1,type="private"),edit_text=AsyncMock()),from_user=SimpleNamespace(id=2),data="year:charts:2026",answer=AsyncMock())
        with patch.object(year_analytics,"_family",AsyncMock(return_value=self.family())):
            await year_analytics.year_callback(callback)
        markup=callback.message.edit_text.await_args.kwargs["reply_markup"]
        callbacks=[button.callback_data for row in markup.inline_keyboard for button in row]
        self.assertIn("yearchart:flow:2026",callbacks);self.assertIn("yearchart:income:2026",callbacks);self.assertIn("year:main:2026",callbacks)

    async def test_income_chart_uses_prepared_sources_and_full_year_total(self):
        data=snapshot([YearMonth(8,5250,400,300)],income_sources=(("Зарплата Сергей",2400),("Зарплата Анна",2100),("Продажа",500),("Возврат",250)))
        message=SimpleNamespace(chat=SimpleNamespace(id=1,type="private"),answer_photo=AsyncMock(),delete=AsyncMock())
        callback=SimpleNamespace(message=message,from_user=SimpleNamespace(id=2),data="yearchart:income:2026",answer=AsyncMock())
        with patch.object(year_analytics,"_family",AsyncMock(return_value=self.family())),patch.object(year_analytics,"get_year_analytics",AsyncMock(return_value=data)) as service,patch.object(year_analytics.asyncio,"to_thread",AsyncMock(return_value=PNG_HEADER+b"chart")) as render:
            await year_analytics.year_chart(callback)
        service.assert_awaited_once_with(7,2026,"Europe/Berlin")
        self.assertEqual(render.await_args.args[1],data.income_sources)
        self.assertEqual(render.await_args.kwargs["currency"],"$")
        self.assertIn("5 250.00 $",message.answer_photo.await_args.kwargs["caption"])

    async def test_empty_income_chart_uses_income_specific_message(self):
        message=SimpleNamespace(chat=SimpleNamespace(id=1,type="private"),answer_photo=AsyncMock(),delete=AsyncMock())
        callback=SimpleNamespace(message=message,from_user=SimpleNamespace(id=2),data="yearchart:income:2026",answer=AsyncMock())
        with patch.object(year_analytics,"_family",AsyncMock(return_value=self.family())),patch.object(year_analytics,"get_year_analytics",AsyncMock(return_value=snapshot())):
            await year_analytics.year_chart(callback)
        message.answer_photo.assert_not_awaited()
        self.assertEqual(callback.answer.await_args.args[0],t("en","chart.no_income"))


if __name__ == "__main__":unittest.main()
