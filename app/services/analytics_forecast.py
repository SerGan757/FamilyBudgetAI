from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class AnalyticsForecast:
    days_remaining: int
    elapsed_percent: int
    spent_percent: int | None
    forecast_expenses: float | None
    forecast_balance: float | None
    pace_delta: int | None


def _round_percent(value: float) -> int:
    return int(value + 0.5)


def current_date(timezone_name: str = "Europe/Berlin") -> date:
    return datetime.now(ZoneInfo(timezone_name)).date()


def calculate_analytics_forecast(
    year: int,
    month: int,
    total_income: float,
    ordinary_expenses: float,
    recurring_expenses: float,
    *,
    today: date | None = None,
) -> AnalyticsForecast:
    """Calculate a calendar-month forecast without changing analytics totals."""
    today = today or current_date()
    selected_month = (year, month)
    current_month = (today.year, today.month)
    days_in_month = monthrange(year, month)[1]
    total_expenses = ordinary_expenses + recurring_expenses

    spent_percent = (
        _round_percent(total_expenses / total_income * 100)
        if total_income > 0
        else None
    )

    if selected_month > current_month:
        return AnalyticsForecast(days_in_month, 0, None, None, None, None)

    if selected_month < current_month:
        forecast_expenses = total_expenses
        forecast_balance = (
            total_income - total_expenses if total_income > 0 else None
        )
        pace_delta = spent_percent - 100 if spent_percent is not None else None
        return AnalyticsForecast(
            0, 100, spent_percent, forecast_expenses, forecast_balance, pace_delta,
        )

    elapsed_days = today.day
    elapsed_percent = _round_percent(elapsed_days / days_in_month * 100)
    forecast_ordinary_expenses = ordinary_expenses / elapsed_days * days_in_month
    forecast_expenses = forecast_ordinary_expenses + recurring_expenses
    forecast_balance = (
        total_income - forecast_expenses if total_income > 0 else None
    )
    elapsed_recurring_expenses = recurring_expenses * elapsed_days / days_in_month
    pace_spent_percent = (
        _round_percent(
            (ordinary_expenses + elapsed_recurring_expenses) / total_income * 100
        )
        if total_income > 0
        else None
    )
    pace_delta = (
        pace_spent_percent - elapsed_percent
        if pace_spent_percent is not None
        else None
    )
    return AnalyticsForecast(
        days_in_month - elapsed_days,
        elapsed_percent,
        spent_percent,
        forecast_expenses,
        forecast_balance,
        pace_delta,
    )
