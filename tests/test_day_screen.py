import unittest
from datetime import date

from app.handlers.statistics import day_keyboard


class DayScreenTests(unittest.TestCase):
    def test_navigation_handles_calendar_boundaries_and_keeps_date_in_pagination(self):
        keyboard = day_keyboard(date(2026, 7, 31), 20, 41)
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
        self.assertIn("day:2026-07-30", callbacks)
        self.assertIn("day:2026-08-01", callbacks)
        self.assertIn("today:2026-07-31:page:0", callbacks)
        self.assertEqual(day_keyboard(date(2024, 2, 29), 0, 0).inline_keyboard[0][1].callback_data, "day:2024-03-01")
