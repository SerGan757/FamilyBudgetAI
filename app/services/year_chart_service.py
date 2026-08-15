from __future__ import annotations

from io import BytesIO
from threading import Lock
import unicodedata

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.ticker import FuncFormatter

from app.services.year_analytics_service import YearAnalytics


_render_lock = Lock()


def chart_category_label(label: str) -> str:
    first, separator, rest = label.partition(" ")
    if separator and first and unicodedata.category(first[0]) in {"So", "Sk"}:
        return rest
    return label


def _money_axis(currency: str):
    return FuncFormatter(lambda value, _: f"{value:,.0f} {currency}".replace(",", " "))


def calendar_series(data: YearAnalytics):
    if not data.months:
        return (), (), (), ()
    by_month = {row.month: row for row in data.months}
    months = tuple(range(data.months[0].month, data.months[-1].month + 1))
    income = tuple(by_month[month].income if month in by_month else None for month in months)
    expense = tuple(by_month[month].expense if month in by_month else None for month in months)
    result = tuple(by_month[month].result if month in by_month else None for month in months)
    return months, income, expense, result


def monthly_income_series(data: YearAnalytics):
    """Return chronological income values, filling intermediate months with zero."""
    if not data.months:
        return (), ()
    by_month = {row.month: row.income for row in data.months}
    months = tuple(range(data.months[0].month, data.months[-1].month + 1))
    return months, tuple(by_month.get(month, 0.0) for month in months)


def _png(draw):
    with _render_lock:
        fig = None
        try:
            fig, ax = plt.subplots(figsize=(9, 6), dpi=150, facecolor="#f8fafc")
            ax.set_facecolor("#f8fafc")
            draw(fig, ax)
            fig.tight_layout()
            output = BytesIO()
            fig.savefig(output, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
            return output.getvalue()
        finally:
            if fig is not None:
                plt.close(fig)


def render_income_expense_chart(data: YearAnalytics, *, month_labels, title, income_label, expense_label, currency):
    if not data.months:
        return None
    months, income, expense, _ = calendar_series(data)

    def draw(_, ax):
        ax.plot(months, income, marker="o", linewidth=2.5, color="#168aad", label=income_label)
        ax.plot(months, expense, marker="o", linewidth=2.5, color="#d97706", label=expense_label)
        ax.set_xticks(months, [month_labels[month - 1] for month in months])
        ax.yaxis.set_major_formatter(_money_axis(currency))
        ax.grid(axis="y", alpha=.22)
        ax.set_title(title, fontsize=16, weight="bold", pad=16)
        ax.legend(frameon=False, ncol=2, loc="upper left")
        ax.spines[["top", "right"]].set_visible(False)

    return _png(draw)


def render_result_chart(data: YearAnalytics, *, month_labels, title, currency):
    if not data.months:
        return None
    months, _, _, result = calendar_series(data)

    def draw(_, ax):
        values = [value if value is not None else 0 for value in result]
        colors = ["#2a9d8f" if value > 0 else "#d1495b" if value < 0 else "#94a3b8" for value in values]
        bars = ax.bar(months, values, color=colors, width=.66)
        for bar, value, original in zip(bars, values, result):
            if original is None:
                bar.set_alpha(.18)
            elif value:
                ax.annotate(f"{value:+,.0f}".replace(",", " "), (bar.get_x()+bar.get_width()/2, value),
                            xytext=(0, 5 if value >= 0 else -14), textcoords="offset points", ha="center", fontsize=9)
        ax.axhline(0, color="#334155", linewidth=1)
        ax.set_xticks(months, [month_labels[month - 1] for month in months])
        ax.yaxis.set_major_formatter(_money_axis(currency))
        ax.grid(axis="y", alpha=.18)
        ax.set_title(title, fontsize=16, weight="bold", pad=16)
        ax.spines[["top", "right"]].set_visible(False)

    return _png(draw)


def render_categories_chart(categories, *, title, currency):
    rows = tuple(categories[:7])
    if not rows or not any(amount > 0 for _, amount in rows):
        return None

    def draw(_, ax):
        labels = [chart_category_label(label) for label, _ in reversed(rows)]
        values = [amount for _, amount in reversed(rows)]
        bars = ax.barh(labels, values, color="#457b9d")
        padding = max(values) * .02 if values else 0
        for bar, value in zip(bars, values):
            ax.text(value + padding, bar.get_y()+bar.get_height()/2,
                    f"{value:,.2f} {currency}".replace(",", " "), va="center", fontsize=9)
        ax.xaxis.set_major_formatter(_money_axis(currency))
        ax.grid(axis="x", alpha=.18)
        ax.set_title(title, fontsize=16, weight="bold", pad=16)
        ax.spines[["top", "right", "left"]].set_visible(False)

    return _png(draw)


def render_income_sources_chart(sources, *, title, currency):
    rows = tuple(sources[:7])
    if not rows or not any(amount > 0 for _, amount in rows):
        return None

    def draw(_, ax):
        labels = [label for label, _ in reversed(rows)]
        values = [amount for _, amount in reversed(rows)]
        bars = ax.barh(labels, values, color="#168aad")
        padding = max(values) * .02 if values else 0
        for bar, value in zip(bars, values):
            ax.text(value + padding, bar.get_y()+bar.get_height()/2,
                    f"{value:,.2f} {currency}".replace(",", " "), va="center", fontsize=9)
        ax.xaxis.set_major_formatter(_money_axis(currency))
        ax.grid(axis="x", alpha=.18)
        ax.set_title(title, fontsize=16, weight="bold", pad=16)
        ax.spines[["top", "right", "left"]].set_visible(False)

    return _png(draw)


def render_monthly_income_chart(data: YearAnalytics, *, month_labels, title, currency):
    months, income = monthly_income_series(data)
    if not months or not any(value > 0 for value in income):
        return None

    def draw(_, ax):
        bars = ax.bar(months, income, color="#168aad", width=.66)
        padding = max(income) * .02 if income else 0
        for bar, value in zip(bars, income):
            if value:
                ax.text(
                    bar.get_x() + bar.get_width() / 2, value + padding,
                    f"{value:,.0f}".replace(",", " "), ha="center", va="bottom", fontsize=9,
                )
        ax.set_xticks(months, [month_labels[month - 1] for month in months])
        ax.yaxis.set_major_formatter(_money_axis(currency))
        ax.grid(axis="y", alpha=.18)
        ax.set_title(title, fontsize=16, weight="bold", pad=16)
        ax.spines[["top", "right"]].set_visible(False)

    return _png(draw)
