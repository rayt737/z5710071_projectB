"""Station 3 (extension) - fuse sentiment into the equity funds.

Baseline (honest, not tuned): a cross-sectional sentiment tilt applied to the
EQUITY minimum-variance fund, equity data only (sentiment does not touch crypto).

Tilt rule at each rebalance date t:
    1. Standardise each stock's sentiment into a rolling z-score over the last
       ``z_window`` trading days, using sentiment up to day t-1 ONLY (the aligned
       panel's values strictly before t; an explicit assertion enforces this).
    2. w_tilt_i = w_base_i * (1 + lambda * z_i), with lambda in {-1, +1}
       (momentum / contrarian).
    3. Clip negatives to 0 and renormalise to sum 1.

lambda is deliberately NOT tuned here - that is future work if we decide to
pursue it. Both settings are reported against the untilted base fund, whichever
way they go (an honest underperformer is a fine result for this baseline).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.portfolios import assert_no_lookahead, performance_metrics, turnover

Z_WINDOW = 60  # trading days for the rolling z-score (stated choice)
WEIGHT_TOL = 1e-6


def tilt_weights(
    base_weights: pd.DataFrame,
    aligned_sentiment: pd.DataFrame,
    lam: float,
    z_window: int = Z_WINDOW,
) -> pd.DataFrame:
    """Apply the sentiment tilt to a base fund's rebalance weights.

    Args:
        base_weights: DataFrame indexed by rebalance date, columns = tickers.
        aligned_sentiment: date x ticker stock sentiment aligned to trading days
            (values reflect only information up to that date). Look-ahead-safe
            here because at rebalance t we only use rows with index < t.
        lam: tilt sign (+1 momentum, -1 contrarian).
        z_window: rolling z-score window in trading days.

    Returns:
        Fused weights (same index/columns as base_weights), long-only, sum 1.
    """
    tickers = list(base_weights.columns)
    n = len(tickers)
    fused_rows = []
    for t, row in base_weights.iterrows():
        w_base = row.to_numpy(dtype=float)
        hist = aligned_sentiment.loc[aligned_sentiment.index < t]
        assert_no_lookahead(hist.index.max(), t)
        win = hist.iloc[-z_window:]
        if len(win) == 0:
            z = np.zeros(n)
        else:
            mu = win.mean().to_numpy(dtype=float)
            sd = win.std(ddof=1).to_numpy(dtype=float)
            last = win.iloc[-1].to_numpy(dtype=float)
            z = np.divide(last - mu, sd, out=np.zeros(n), where=sd > 1e-12)
            z = np.nan_to_num(z, nan=0.0, posinf=0.0, neginf=0.0)
        w_tilt = w_base * (1.0 + lam * z)
        w_tilt = np.clip(w_tilt, 0.0, None)
        s = w_tilt.sum()
        w_tilt = w_tilt / s if s > 0 else w_base
        assert np.all(w_tilt >= -WEIGHT_TOL), "fusion produced a negative weight"
        assert abs(w_tilt.sum() - 1.0) <= WEIGHT_TOL, "fusion weights do not sum to 1"
        fused_rows.append(pd.Series(w_tilt, index=tickers, name=t))
    fused = pd.DataFrame(fused_rows)
    fused.index.name = "date"  # same convention as portfolios.oos_backtest weights
    return fused


def weights_to_daily_returns(
    weights: pd.DataFrame,
    returns_wide: pd.DataFrame,
) -> pd.Series:
    """Map rebalance weights onto daily returns from the first rebalance onward.

    Each day uses the weight vector of the most recent rebalance on or before it
    (identical weighting logic to portfolios.oos_backtest).
    """
    rebal_dates = list(weights.index)
    start = rebal_dates[0]
    oos_dates = returns_wide.index[returns_wide.index >= start]
    pos = pd.Index(rebal_dates).searchsorted(oos_dates, side="right") - 1
    wm = weights.to_numpy()[pos]
    daily = returns_wide.loc[oos_dates]
    assert not daily.isna().any().any(), "NaN return present in the fused OOS window"
    return pd.Series((wm * daily.to_numpy()).sum(axis=1), index=oos_dates)


def run_fusion(
    returns_equity: pd.DataFrame,
    base_weights: pd.DataFrame,
    aligned_sentiment: pd.DataFrame,
    lam: float,
    z_window: int = Z_WINDOW,
) -> tuple[pd.Series, pd.DataFrame]:
    """Full fusion run: tilt weights, then compute the OOS daily returns.

    Returns (fused_daily_returns, fused_weights).
    """
    fused_weights = tilt_weights(base_weights, aligned_sentiment, lam, z_window)
    fused_returns = weights_to_daily_returns(fused_weights, returns_equity)
    return fused_returns, fused_weights


def build_fusion_comparison(
    base_returns: pd.Series,
    base_weights: pd.DataFrame,
    fused_results: dict[str, tuple[pd.Series, pd.DataFrame]],
    ann_factor: int = 252,
) -> pd.DataFrame:
    """Base vs fused performance table (Sharpe/return/vol) for both lambda values."""
    rows = []
    m = performance_metrics(base_returns, ann_factor)
    m["fund"] = "equity_min_variance_base"
    m["lambda"] = 0.0
    m["turnover"] = turnover(base_weights)
    rows.append(m)
    for label, (ret, w) in fused_results.items():
        mm = performance_metrics(ret, ann_factor)
        mm["fund"] = f"equity_min_variance_{label}"
        mm["lambda"] = 1.0 if label == "momentum" else -1.0
        mm["turnover"] = turnover(w)
        rows.append(mm)
    cols = ["fund", "lambda", "annualised_return", "annualised_volatility",
            "sharpe_ratio", "max_drawdown", "total_return", "turnover"]
    return pd.DataFrame(rows)[cols]
