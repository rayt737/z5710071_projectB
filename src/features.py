"""Station 2 - Feature Engineering & Text Assembly (ported from Part A).

Builds:
1. Daily returns (simple pct_change per ticker) - the one required feature.
2. Assembles headlines into a daily panel per ticker and sector, mapping every
   headline to its equity trading day (same day if a trading day, else the next
   trading day). Scoring the text is Station 3 (src/sentiment.py).

Key rules:
- Keep raw headline text uncleaned (VADER needs case, punctuation, negation cues).
- The headline mapping is vectorised (searchsorted on the trading calendar), so it
  scales to ~147k headlines instead of per-row Python loops.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def daily_returns(
    prices: pd.DataFrame,
    price_col: str = "adjClose",
) -> pd.DataFrame:
    """Compute simple daily returns per ticker using adjClose.

    r_t = (P_t - P_{t-1}) / P_{t-1}, computed within each ticker group.
    First return per ticker is NaN.
    """
    df = prices.sort_values(["ticker", "date"]).copy()
    df["return"] = df.groupby("ticker")[price_col].pct_change()
    return df


def returns_to_wide(
    returns_long: pd.DataFrame,
    value_col: str = "return",
) -> pd.DataFrame:
    """Pivot a long (date, ticker, return) frame into a wide date x ticker panel.

    Returns a DataFrame indexed by ascending date with one column per ticker.
    """
    wide = returns_long.dropna(subset=[value_col]).pivot(
        index="date", columns="ticker", values=value_col
    )
    wide = wide.sort_index()
    wide.index.name = "date"
    wide.columns.name = "ticker"
    return wide


def assemble_headline_panel(
    headlines: pd.DataFrame,
    equity_trading_dates: pd.DatetimeIndex | list,
    tz_aware: bool = True,
) -> pd.DataFrame:
    """Assemble headlines into a daily panel per ticker and sector.

    Mapping rule: if the (tz-normalised) headline date IS an equity trading day,
    keep it there; otherwise roll forward to the next trading day.

    Returns a long DataFrame with columns: date (trading day), ticker, sector,
    title (raw text), url, publisher.
    """
    df = headlines.copy()
    dates = pd.DatetimeIndex(sorted(equity_trading_dates))
    date_np = dates.values.astype("datetime64[ns]")

    if tz_aware and df["date"].dt.tz is not None:
        df["date"] = pd.to_datetime(df["date"]).dt.tz_convert("UTC").dt.tz_localize(None)
    else:
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)

    hd_np = df["date"].values.astype("datetime64[ns]")
    idx = np.searchsorted(date_np, hd_np, side="left")
    idx = np.clip(idx, 0, len(dates) - 1)
    idx[date_np[idx] < hd_np] = idx[date_np[idx] < hd_np] + 1
    idx = np.clip(idx, 0, len(dates) - 1)
    df["date"] = dates[idx]

    df = df.reset_index(drop=True)
    return df[["date", "ticker", "sector", "title", "url", "publisher"]]
