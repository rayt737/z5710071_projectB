"""Shared presentation formatting for the Station 4 app (prompt_06).

Single source of truth for how point-in-time dates are rendered as text
("01 January 2021", never ISO) and how raw metric column names map to the
human labels users see ("sharpe_ratio" -> "Sharpe Ratio"). Chart axis tick
formatting is deliberately NOT routed through format_date - axes stay on
Plotly's compact date-axis formatting, because a 3-year daily x-axis written
out in full would be unreadable (prompt_06 item 1).
"""
from __future__ import annotations

import pandas as pd

METRIC_LABELS = {
    "annualised_return": "Annualised Return",
    "annualised_volatility": "Annualised Volatility",
    "sharpe_ratio": "Sharpe Ratio",
    "max_drawdown": "Max Drawdown",
}


def format_date(value) -> str:
    """Render a point-in-time date as text, e.g. ``01 January 2021``.

    Accepts a datetime.date, a pandas Timestamp, or an ISO string such as
    ``2021-01-04``. Any time-of-day component is ignored (dates only).
    """
    return pd.Timestamp(value).strftime("%d %B %Y")


def metric_label(column: str) -> str:
    """Human label for a raw metric column name (identity if unknown)."""
    return METRIC_LABELS.get(column, column)
