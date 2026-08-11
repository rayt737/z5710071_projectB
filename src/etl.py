"""Station 1 - Data Lake / ETL: load, clean, and integrity-check the data.

All data is pulled through src.data_access (which caches after one network hit).
This module adds cleaning, integrity checks, timezone normalisation, and
calendar handling for the combined equity + crypto return panel.

Key rules:
- Compute returns WITHIN each panel (equity on 252-day calendar, crypto on 365-day).
- Left-merge crypto returns onto the equity trading calendar (drops weekend-only crypto moves).
- Never merge price levels across calendars and difference afterwards.
- Cap sample at 2023-12-31 (10 stray crypto rows dated 2024-01-01).
"""
from __future__ import annotations

import pandas as pd

from src import data_access

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SAMPLE_END = pd.Timestamp("2023-12-31")
EQUITY_ANNUAL_FACTOR = 252
CRYPTO_ANNUAL_FACTOR = 365
OUTLIER_Z_THRESHOLD = 4.0  # returns beyond |z|>4 flagged as extreme


# ---------------------------------------------------------------------------
# Loaders with integrity checks
# ---------------------------------------------------------------------------

def load_clean_equities() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load equity prices, run integrity checks, return (clean_df, integrity_log).

    Checks:
    - Missing-date audit (expected ~252 business days/year per ticker)
    - Duplicate ticker-date check
    - Outlier/extreme-value screen on returns (flag, verify OHLCV, keep)
    """
    df = data_access.load_equity_prices().copy()
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)  # ensure tz-naive

    integrity_rows = []

    # --- Missing-date audit ---
    expected_dates = pd.bdate_range(df["date"].min(), df["date"].max())
    for ticker in sorted(df["ticker"].unique()):
        tk_dates = set(df.loc[df["ticker"] == ticker, "date"])
        missing = sorted(set(expected_dates) - tk_dates)
        if missing:
            integrity_rows.append({
                "check": "missing_dates",
                "dataset": "equity",
                "ticker": ticker,
                "count": len(missing),
                "pct": round(len(missing) / len(expected_dates) * 100, 2),
                "detail": f"{len(missing)} missing of {len(expected_dates)} expected",
            })
    agg_missing = sum(r["count"] for r in integrity_rows if r["check"] == "missing_dates")
    integrity_rows.append({
        "check": "missing_dates",
        "dataset": "equity",
        "ticker": "ALL",
        "count": agg_missing,
        "pct": round(agg_missing / (len(expected_dates) * df["ticker"].nunique()) * 100, 2),
        "detail": f"aggregate: {agg_missing} gaps across {df['ticker'].nunique()} tickers",
    })

    # --- Duplicate check (ticker, date) ---
    dup_mask = df.duplicated(subset=["ticker", "date"], keep=False)
    n_dups = dup_mask.sum()
    integrity_rows.append({
        "check": "duplicates",
        "dataset": "equity",
        "ticker": "ALL",
        "count": int(n_dups),
        "pct": round(n_dups / len(df) * 100, 3),
        "detail": f"{n_dups} duplicate ticker-date rows out of {len(df)}",
    })
    if n_dups > 0:
        df = df.drop_duplicates(subset=["ticker", "date"], keep="first").reset_index(drop=True)

    # --- Outlier screen on returns ---
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    df["return"] = df.groupby("ticker")["adjClose"].pct_change()
    ret_valid = df["return"].dropna()
    z_all = (df["return"] - ret_valid.mean()) / ret_valid.std()
    outlier_mask = z_all.abs() > OUTLIER_Z_THRESHOLD
    n_outliers = outlier_mask.sum()
    outlier_df = df.loc[outlier_mask, ["date", "ticker", "return"]].copy()

    # Verify OHLCV consistency for flagged rows
    flagged = df.loc[outlier_mask].copy()
    inconsistent = flagged[
        (flagged["low"] > flagged["close"]) |
        (flagged["close"] > flagged["high"]) |
        (flagged["volume"] < 0)
    ]
    n_inconsistent = len(inconsistent)

    integrity_rows.append({
        "check": "outliers",
        "dataset": "equity",
        "ticker": "ALL",
        "count": int(n_outliers),
        "pct": round(n_outliers / len(ret_valid) * 100, 3),
        "detail": f"{n_outliers} returns beyond |z|>{OUTLIER_Z_THRESHOLD}, "
                  f"{n_inconsistent} OHLCV-inconsistent (0 expected); all kept",
    })

    # Document biggest outlier clusters (by date)
    if n_outliers > 0:
        top_dates = outlier_df.groupby("date").size().sort_values(ascending=False).head(5)
        for dt, cnt in top_dates.items():
            integrity_rows.append({
                "check": "outlier_cluster",
                "dataset": "equity",
                "ticker": "ALL",
                "count": int(cnt),
                "pct": 0,
                "detail": f"{cnt} extreme returns on {dt.strftime('%Y-%m-%d')}",
            })

    integrity_log = pd.DataFrame(integrity_rows)
    return df, integrity_log


def load_clean_crypto() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load crypto prices, integrity-check, cap at 2023-12-31.

    Returns (clean_df, integrity_log).

    Checks:
    - Missing-date audit (crypto trades 365 days/year)
    - Duplicate ticker-date check
    - Outlier/extreme-value screen on returns
    """
    df = data_access.load_crypto_prices().copy()
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)

    integrity_rows = []

    # --- Cap at 2023-12-31 ---
    pre_cap = len(df)
    df = df[df["date"] <= SAMPLE_END].reset_index(drop=True)
    dropped = pre_cap - len(df)
    if dropped > 0:
        integrity_rows.append({
            "check": "sample_cap",
            "dataset": "crypto",
            "ticker": "ALL",
            "count": int(dropped),
            "pct": round(dropped / pre_cap * 100, 3),
            "detail": f"Dropped {dropped} rows dated after 2023-12-31 (stray 2024-01-01 entries)",
        })

    # --- Missing-date audit (365 days/year) ---
    expected_dates = pd.date_range(df["date"].min(), df["date"].max(), freq="D")
    for ticker in sorted(df["ticker"].unique()):
        tk_dates = set(df.loc[df["ticker"] == ticker, "date"])
        missing = sorted(set(expected_dates) - tk_dates)
        if missing:
            integrity_rows.append({
                "check": "missing_dates",
                "dataset": "crypto",
                "ticker": ticker,
                "count": len(missing),
                "pct": round(len(missing) / len(expected_dates) * 100, 2),
                "detail": f"{len(missing)} missing of {len(expected_dates)} expected",
            })
    agg_missing = sum(r["count"] for r in integrity_rows if r["check"] == "missing_dates")
    integrity_rows.append({
        "check": "missing_dates",
        "dataset": "crypto",
        "ticker": "ALL",
        "count": agg_missing,
        "pct": round(agg_missing / (len(expected_dates) * df["ticker"].nunique()) * 100, 2),
        "detail": f"aggregate: {agg_missing} gaps across {df['ticker'].nunique()} tickers",
    })

    # --- Duplicate check (ticker, date) ---
    dup_mask = df.duplicated(subset=["ticker", "date"], keep=False)
    n_dups = dup_mask.sum()
    integrity_rows.append({
        "check": "duplicates",
        "dataset": "crypto",
        "ticker": "ALL",
        "count": int(n_dups),
        "pct": round(n_dups / len(df) * 100, 3),
        "detail": f"{n_dups} duplicate ticker-date rows out of {len(df)}",
    })
    if n_dups > 0:
        df = df.drop_duplicates(subset=["ticker", "date"], keep="first").reset_index(drop=True)

    # --- Outlier screen ---
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    df["return"] = df.groupby("ticker")["adjClose"].pct_change()
    ret_valid = df["return"].dropna()
    z_all = (df["return"] - ret_valid.mean()) / ret_valid.std()
    outlier_mask = z_all.abs() > OUTLIER_Z_THRESHOLD
    n_outliers = outlier_mask.sum()
    outlier_df = df.loc[outlier_mask, ["date", "ticker", "return"]].copy()

    flagged = df.loc[outlier_mask].copy()
    inconsistent = flagged[
        (flagged["low"] > flagged["close"]) |
        (flagged["close"] > flagged["high"]) |
        (flagged["volume"] < 0)
    ]
    n_inconsistent = len(inconsistent)

    integrity_rows.append({
        "check": "outliers",
        "dataset": "crypto",
        "ticker": "ALL",
        "count": int(n_outliers),
        "pct": round(n_outliers / len(ret_valid) * 100, 3),
        "detail": f"{n_outliers} returns beyond |z|>{OUTLIER_Z_THRESHOLD}, "
                  f"{n_inconsistent} OHLCV-inconsistent; all kept",
    })

    if n_outliers > 0:
        top_dates = outlier_df.groupby("date").size().sort_values(ascending=False).head(5)
        for dt, cnt in top_dates.items():
            integrity_rows.append({
                "check": "outlier_cluster",
                "dataset": "crypto",
                "ticker": "ALL",
                "count": int(cnt),
                "pct": 0,
                "detail": f"{cnt} extreme returns on {dt.strftime('%Y-%m-%d')}",
            })

    integrity_log = pd.DataFrame(integrity_rows)
    return df, integrity_log


def load_clean_headlines() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load news headlines, dedup on (ticker, date, title), strip tz.

    Returns (clean_df, integrity_log). Known: ~2,847 exact duplicates on
    ticker+date+title. Keep first occurrence.
    """
    df = data_access.load_news_headlines().copy()

    integrity_rows = []

    # --- Strip timezone (dates are UTC-aware; prices are tz-naive) ---
    # Conversion: UTC-aware datetime64[us, UTC] -> tz-naive datetime64[ns]
    # via tz_convert("UTC").dt.tz_localize(None). Preserves wall-clock dates.
    df["date"] = pd.to_datetime(df["date"]).dt.tz_convert("UTC").dt.tz_localize(None)

    n_before = len(df)

    # --- Duplicate check (ticker, date, title) ---
    dup_mask = df.duplicated(subset=["ticker", "date", "title"], keep="first")
    n_dups = dup_mask.sum()
    integrity_rows.append({
        "check": "duplicates",
        "dataset": "headlines",
        "ticker": "ALL",
        "count": int(n_dups),
        "pct": round(n_dups / n_before * 100, 3),
        "detail": f"{n_dups} exact duplicates on (ticker, date, title) "
                  f"removed; kept first occurrence",
    })
    df = df[~dup_mask].reset_index(drop=True)

    integrity_rows.append({
        "check": "post_dedup",
        "dataset": "headlines",
        "ticker": "ALL",
        "count": len(df),
        "pct": round(len(df) / n_before * 100, 3),
        "detail": f"Rows after dedup: {len(df)} (from {n_before})",
    })

    integrity_log = pd.DataFrame(integrity_rows)
    return df, integrity_log


# ---------------------------------------------------------------------------
# Dataset inventory
# ---------------------------------------------------------------------------

def build_dataset_inventory(
    eq: pd.DataFrame,
    cr: pd.DataFrame,
    nl: pd.DataFrame,
) -> pd.DataFrame:
    """Build the dataset_inventory.csv table.

    One row per dataset: rows, date span, frequency, coverage.
    """
    rows = [
        {
            "dataset": "equity_prices",
            "rows": len(eq),
            "date_start": eq["date"].min().strftime("%Y-%m-%d"),
            "date_end": eq["date"].max().strftime("%Y-%m-%d"),
            "frequency": "daily (252 biz days/yr)",
            "coverage": f"{eq['ticker'].nunique()} tickers, {eq['sector'].nunique()} sectors",
            "source": "data_access.load_equity_prices()",
        },
        {
            "dataset": "crypto_prices",
            "rows": len(cr),
            "date_start": cr["date"].min().strftime("%Y-%m-%d"),
            "date_end": cr["date"].max().strftime("%Y-%m-%d"),
            "frequency": "daily (365 days/yr)",
            "coverage": f"{cr['ticker'].nunique()} tickers, no sector",
            "source": "data_access.load_crypto_prices()",
        },
        {
            "dataset": "news_headlines",
            "rows": len(nl),
            "date_start": nl["date"].min().strftime("%Y-%m-%d"),
            "date_end": nl["date"].max().strftime("%Y-%m-%d"),
            "frequency": "daily (variable per ticker)",
            "coverage": (f"{nl['ticker'].nunique()} tickers, "
                         f"{nl['sector'].nunique()} sectors, "
                         f"{nl['publisher'].nunique()} publishers"),
            "source": "data_access.load_news_headlines()",
        },
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Combined return panel (calendar handling)
# ---------------------------------------------------------------------------

def build_combined_returns_panel(
    eq: pd.DataFrame,
    cr: pd.DataFrame,
) -> pd.DataFrame:
    """Build the combined returns panel.

    CRITICAL calendar handling:
    1. Compute equity returns on the equity calendar (business days).
    2. Compute crypto returns on the crypto calendar (365 days).
    3. Left-merge crypto returns onto the equity trading-day calendar.
    4. This intentionally drops weekend-only crypto moves.

    Returns a DataFrame indexed by equity trading date with columns for each
    ticker's daily return.
    """
    # Step 1: Equity returns (already computed in load_clean_equities as 'return')
    eq_returns = eq[["date", "ticker", "return"]].copy()
    eq_returns = eq_returns.dropna(subset=["return"])
    eq_wide = eq_returns.pivot(index="date", columns="ticker", values="return")
    eq_wide.index.name = "date"

    # Step 2: Crypto returns (compute on 365-day calendar)
    cr_returns = cr[["date", "ticker", "return"]].copy()
    cr_returns = cr_returns.dropna(subset=["return"])
    cr_wide = cr_returns.pivot(index="date", columns="ticker", values="return")

    # Step 3: Left-merge crypto returns onto equity trading calendar
    # Reindex crypto to equity dates only (forward-fill if needed, but
    # left-join on equity dates naturally drops weekend crypto moves)
    equity_dates = eq_wide.index.sort_values()
    cr_aligned = cr_wide.reindex(equity_dates)

    # Step 4: Combine
    combined = pd.concat([eq_wide, cr_aligned], axis=1)
    combined.columns.name = "ticker"

    return combined.reset_index()
