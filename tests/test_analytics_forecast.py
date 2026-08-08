import math
import unittest
from datetime import date

from app.services.analytics_forecast import calculate_analytics_forecast


class AnalyticsForecastTests(unittest.TestCase):
    def test_current_month_calculates_forecast_and_above_plan(self):
        result = calculate_analytics_forecast(
            2026, 8, 1000, 400, 0, today=date(2026, 8, 8),
        )
        self.assertEqual(result.days_remaining, 23)
        self.assertEqual(result.elapsed_percent, 26)
        self.assertEqual(result.spent_percent, 40)
        self.assertEqual(result.forecast_expenses, 1550)
        self.assertEqual(result.forecast_balance, -550)
        self.assertEqual(result.pace_delta, 14)

    def test_pace_economy_and_on_plan(self):
        economy = calculate_analytics_forecast(
            2026, 4, 1000, 350, 0, today=date(2026, 4, 15),
        )
        on_plan = calculate_analytics_forecast(
            2026, 4, 1000, 500, 0, today=date(2026, 4, 15),
        )
        self.assertEqual(economy.pace_delta, -15)
        self.assertEqual(on_plan.pace_delta, 0)

    def test_no_income_omits_income_based_values_without_non_finite_numbers(self):
        result = calculate_analytics_forecast(
            2026, 8, 0, 400, 0, today=date(2026, 8, 8),
        )
        self.assertIsNone(result.spent_percent)
        self.assertIsNone(result.forecast_balance)
        self.assertIsNone(result.pace_delta)
        self.assertTrue(math.isfinite(result.forecast_expenses))

    def test_past_month_uses_actual_totals(self):
        result = calculate_analytics_forecast(
            2026, 7, 1000, 400, 0, today=date(2026, 8, 8),
        )
        self.assertEqual(result.days_remaining, 0)
        self.assertEqual(result.elapsed_percent, 100)
        self.assertEqual(result.forecast_expenses, 400)
        self.assertEqual(result.forecast_balance, 600)
        self.assertEqual(result.pace_delta, -60)

    def test_future_month_only_has_calendar_progress(self):
        result = calculate_analytics_forecast(
            2026, 9, 1000, 400, 0, today=date(2026, 8, 8),
        )
        self.assertEqual((result.days_remaining, result.elapsed_percent), (30, 0))
        self.assertIsNone(result.spent_percent)
        self.assertIsNone(result.forecast_expenses)
        self.assertIsNone(result.forecast_balance)
        self.assertIsNone(result.pace_delta)

    def test_month_boundaries_and_lengths(self):
        cases = (
            (date(2026, 1, 1), 30, 3),
            (date(2026, 1, 31), 0, 100),
            (date(2026, 2, 1), 27, 4),
            (date(2024, 2, 1), 28, 3),
            (date(2026, 4, 1), 29, 3),
            (date(2026, 8, 1), 30, 3),
        )
        for today, days_remaining, elapsed in cases:
            with self.subTest(today=today):
                result = calculate_analytics_forecast(
                    today.year, today.month, 100, 1, 0, today=today,
                )
                self.assertEqual(result.days_remaining, days_remaining)
                self.assertEqual(result.elapsed_percent, elapsed)

    def test_recurring_expenses_are_added_once_not_extrapolated(self):
        result = calculate_analytics_forecast(
            2026, 8, 4146, 745.60, 1908.36, today=date(2026, 8, 8),
        )
        self.assertAlmostEqual(result.forecast_expenses, 4797.56)
        self.assertAlmostEqual(result.forecast_balance, -651.56)
        self.assertEqual(result.spent_percent, 64)
        self.assertEqual(result.pace_delta, 4)

    def test_only_ordinary_expenses_are_scaled_by_elapsed_days(self):
        result = calculate_analytics_forecast(
            2026, 8, 5000, 800, 2000, today=date(2026, 8, 8),
        )
        self.assertEqual(result.forecast_expenses, 5100)


if __name__ == "__main__":
    unittest.main()
