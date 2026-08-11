"""Station 3 (extension, prompt_02) - volatility-targeting overlay.

Volatility targeting scales a base fund's daily returns by a factor that de-risks
in high-volatility regimes and modestly scales up in calm ones. It is an OVERLAY
on an existing fund's return series, not a separate optimiser (see Moreira &
Muir, 2017 - the same idea the brief cites for this extension).

Design (stated choices, per prompt_02, corrected in prompt_log Entry 7):
- **Target volatility**: annualised realised vol over the base fund's INITIAL
  ESTIMATION WINDOW ONLY - the same first-year window (252 trading days for
  equity/combined, 365 for crypto) already used to set the fund's very first
  out-of-sample weights, and nothing after it. The target is fixed ONCE, before
  live trading starts, and never recomputed. It therefore contains no
  out-of-sample information. (The earlier full-sample target was look-ahead:
  it could only be known once the whole future - including the 2022 crash - had
  happened, which biased k_t up before the crash. See ai/prompt_log.md Entry 7.)
- **Full-history overlay**: the overlay runs on the fund's FULL return history -
  pre-live returns (first-rebalance weights applied to the estimation-window
  asset returns, fully known before day 1) concatenated with the out-of-sample
  returns. Outputs are sliced back to the out-of-sample period afterwards.
- **Trailing realised vol**: 60-trading-day rolling std of the fund's daily
  returns, annualised with the fund's calendar factor.
- **No look-ahead**: the factor for day t uses only returns strictly before t
  (the rolling window ends at t-1); an explicit assertion enforces it, and the
  target is asserted to depend on nothing past the initial window.
- **Scaling factor**: k_t = target_vol / realised_vol_(t-1), clipped to
  [0.5, 1.5] so the overlay stays a genuine "smoothing" tool - partial
  de-risking in high-vol regimes, modest scale-up in calm ones - without
  introducing real leverage/margin complexity into a long-only retail product.
  During the trailing-window warm-up (only the pre-live days at the very start
  of the full history) k = 1.0 (no scaling), the neutral choice.
- **Scaled return**: r_t^scaled = k_t * r_t.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.portfolios import (
    assert_no_lookahead,
    parse_fund_id,
    performance_metrics,
)

TRAILING_WINDOW = 60        # trading days for realised volatility
CLIP_BAND = (0.5, 1.5)      # k_t clip band (stated choice)


def realised_vol(
    returns: pd.Series,
    ann_factor: int,
    window: int = TRAILING_WINDOW,
) -> pd.Series:
    """Trailing annualised realised vol, using only returns strictly before t.

    At each day t the window covers [t-window, t-1] (returns shifted by one),
    so no information from day t leaks into the factor.
    """
    r = returns.dropna()
    trailing = r.shift(1).rolling(window, min_periods=window).std(ddof=1)
    return trailing * np.sqrt(ann_factor)


def scaling_factor(
    returns: pd.Series,
    target_vol: float,
    ann_factor: int,
    window: int = TRAILING_WINDOW,
    clip: tuple[float, float] = CLIP_BAND,
) -> pd.Series:
    """k_t = clip(target_vol / realised_vol_(t-1), clip[0], clip[1]).

    Explicit no-look-ahead assertion: the last return used for day t is the
    return at t-1, which is strictly before t.
    """
    r = returns.dropna()
    real = realised_vol(r, ann_factor, window)
    k = target_vol / real
    k = k.clip(*clip)
    k = k.fillna(1.0)  # warm-up: no scaling until the trailing window fills

    for t in r.index:
        pos = r.index.get_loc(t)
        if pos > 0:
            assert_no_lookahead(r.index[pos - 1], t)
    return k


def target_vol_of(
    fund_returns: pd.Series,
    estimation_window: int,
    ann_factor: int,
) -> float:
    """Annualised realised vol over the FIRST ``estimation_window`` days ONLY.

    The target is a single constant fixed before the out-of-sample period
    begins: it uses only the same pre-live estimation window that set the fund's
    first weights, and nothing after it. An explicit assertion enforces that no
    date beyond the initial window contributes to the number.

    Raises ValueError if the series is shorter than the estimation window plus
    one live day (there must be at least one out-of-sample day to anchor the
    causal check against).
    """
    r = fund_returns.dropna()
    if len(r) < estimation_window + 1:
        raise ValueError(
            f"need at least {estimation_window + 1} days of fund history "
            f"(initial window + one live day) to set a causal target; got {len(r)}")
    window = r.iloc[:estimation_window]
    # Causal assertion: the last date used by the target is strictly before the
    # first date that is NOT in the initial window (the start of live trading).
    assert_no_lookahead(window.index.max(), r.index[estimation_window])
    return float(window.std(ddof=1) * np.sqrt(ann_factor))


def apply_overlay(
    full_returns: pd.Series,
    ann_factor: int,
    estimation_window: int,
    *,
    target: float | None = None,
    window: int = TRAILING_WINDOW,
    clip: tuple[float, float] = CLIP_BAND,
) -> tuple[pd.Series, pd.Series, float]:
    """Apply the overlay over the fund's FULL history; target from the initial window.

    Returns (scaled_returns, k_series, target_vol). The target defaults to the
    annualised vol of the first ``estimation_window`` days (pre-live, causal);
    k_t is clipped to the band and set to 1.0 during the trailing-window warm-up
    at the very start of the full history.
    """
    if target is None:
        target = target_vol_of(full_returns, estimation_window, ann_factor)
    k = scaling_factor(full_returns, target, ann_factor, window, clip)
    scaled = k * full_returns
    return scaled, k, target


def build_vol_target_comparison(
    funds: dict[str, tuple[pd.Series, pd.Series]],
    ann_factors: dict[str, int],
    targets: dict[str, float],
) -> pd.DataFrame:
    """Base vs vol-targeted performance table, one pair per fund.

    ``funds`` maps a label -> (base_returns, vol_targeted_returns) and
    ``targets`` maps a label -> the causal initial-window target vol. Column
    shape mirrors fusion_comparison.csv (same performance metrics), with a
    `target_vol` column instead of `lambda`.
    """
    rows = []
    for label, (base, scaled) in funds.items():
        family = parse_fund_id(label)[0]
        ann = ann_factors[family]
        mb = performance_metrics(base, ann)
        mb["fund"] = f"{label}_base"
        mb["target_vol"] = np.nan
        rows.append(mb)
        ms = performance_metrics(scaled, ann)
        ms["fund"] = f"{label}_vol_targeted"
        ms["target_vol"] = targets[label]
        rows.append(ms)
    cols = ["fund", "target_vol", "annualised_return", "annualised_volatility",
            "sharpe_ratio", "max_drawdown", "total_return"]
    return pd.DataFrame(rows)[cols]
