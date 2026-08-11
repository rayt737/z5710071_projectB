"""Station 3 - funds: optimal portfolios + walk-forward out-of-sample backtest.

Twenty-two funds: three universes (Equity, Crypto, Combined) x four optimisation
methods (Equal-weight, Minimum-variance, Maximum-Sharpe, Risk parity) plus five
prompt_02 grouping families x two methods (Equal-weight, Risk parity).

Backtest rules (see PROJECT_BRIEF.md / ai/prompts/prompt_01.md):
- Walk-forward, expanding window. Initial estimation window = first year of daily
  returns (252 trading days for equity/combined, 365 days for crypto).
- Rebalance monthly on the first trading day of each month (state your choice).
- Weights on day t are formed only from data STRICTLY BEFORE t; look-ahead is
  caught by explicit assertions, not by careful indexing.
- Long-only, fully invested: w >= 0 and sum(w) = 1 at every rebalance.
- Risk-free rate assumed 0 for the Sharpe ratio (state your choice).
- Annualise equity and combined with sqrt(252), crypto with sqrt(365).
- Optimisers are solved on percent-scaled returns (x100) so the solvers do not
  silently stall below tolerance on tiny daily-return covariances (known trap).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, minimize

RF = 0.0  # risk-free rate assumption for the Sharpe ratio (stated choice)

EQUITY_ANNUAL_FACTOR = 252
CRYPTO_ANNUAL_FACTOR = 365
INITIAL_WINDOW_EQUITY = 252   # first year of equity/combined daily returns
INITIAL_WINDOW_CRYPTO = 365   # first year of crypto daily returns

METHODS = ["equal_weight", "min_variance", "max_sharpe", "risk_parity"]
# The five new grouping families (prompt_02) use ONLY the two methods that need
# no return/risk estimate, so they stay "fair" in a no-market-cap dataset:
# equal-weight and risk parity. The three core families keep all four methods.
GROUP_METHODS = ["equal_weight", "risk_parity"]

FAMILIES = [
    "equity", "crypto", "combined",
    "defensive", "cyclical", "growth_sensitive", "payments", "web3infra",
]

METHOD_LABELS = {
    "equal_weight": "Equal-Weight",
    "min_variance": "Minimum-Variance",
    "max_sharpe": "Maximum-Sharpe",
    "risk_parity": "Risk Parity",
}
FAMILY_LABELS = {
    "equity": "Equity", "crypto": "Crypto", "combined": "Combined",
    "defensive": "Defensive", "cyclical": "Cyclical",
    "growth_sensitive": "Growth/Sensitive",
    "payments": "Payment Infrastructure", "web3infra": "Web3 Infrastructure",
}

# Annualisation + initial-window factors per family (equity-calendar clusters
# use sqrt(252); crypto-theme funds use sqrt(365), matching their universe).
ANNUAL_FACTORS = {
    "equity": 252, "crypto": 365, "combined": 252,
    "defensive": 252, "cyclical": 252, "growth_sensitive": 252,
    "payments": 365, "web3infra": 365,
}
INITIAL_WINDOWS = {
    "equity": INITIAL_WINDOW_EQUITY, "crypto": INITIAL_WINDOW_CRYPTO,
    "combined": INITIAL_WINDOW_EQUITY,
    "defensive": INITIAL_WINDOW_EQUITY, "cyclical": INITIAL_WINDOW_EQUITY,
    "growth_sensitive": INITIAL_WINDOW_EQUITY,
    "payments": INITIAL_WINDOW_CRYPTO, "web3infra": INITIAL_WINDOW_CRYPTO,
}

# Equity sector-cluster membership, adapted from the Cyclical/Defensive/
# Sensitive super-sector framework (Fidelity/MSCI-style GICS groupings).
# Membership is DERIVED from the `sector` column in the data (see
# group_universe_tickers); these are the sector labels, not ticker lists.
# Judgement call: this dataset merges Consumer Staples and Discretionary into a
# single `Consumer` sector, so `Consumer` sits in Defensive as a stated
# simplification, not a textbook-exact GICS mapping.
SECTOR_CLUSTERS = {
    "defensive": ["Healthcare", "Utilities", "Consumer"],
    "cyclical": ["Financials", "Industrials", "Materials", "RealEstate"],
    "growth_sensitive": ["Tech", "Comm", "Energy"],
}

# Crypto thematic funds (explicit ticker lists; BTC-USD is excluded from both -
# it stays only in the original 10-coin `crypto` universe funds). Judgement
# call: TRX-USD is architecturally a smart-contract platform, but its dominant
# real-world usage is stablecoin/payment settlement, so it sits in Web3 rather
# than Payments - defensible either way, stated rather than presented as clean.
CRYPTO_THEMES = {
    "payments": ["XRP-USD", "LTC-USD", "BCH-USD", "XLM-USD"],
    "web3infra": ["ETH-USD", "ADA-USD", "ETC-USD", "TRX-USD", "EOS-USD"],
}

WEIGHT_TOL = 1e-6      # tolerance for sum(w) ~ 1 and w in [0,1]
METHOD_DIFF_TOL = 1e-4  # methods must differ from each other by more than this


def group_universe_tickers(
    eq: pd.DataFrame,
    cr: pd.DataFrame,
    family: str,
) -> list[str]:
    """Tickers belonging to a grouping family, derived from the data.

    Sector clusters derive tickers programmatically from the `sector` column of
    the equity price frame (no hardcoded ticker lists). Crypto themes use the
    explicit ticker lists in CRYPTO_THEMES, filtered to those present in the
    crypto frame.
    """
    if family in SECTOR_CLUSTERS:
        sectors = set(SECTOR_CLUSTERS[family])
        return sorted(eq.loc[eq["sector"].isin(sectors), "ticker"].unique())
    if family in CRYPTO_THEMES:
        have = set(cr["ticker"].unique())
        return [t for t in CRYPTO_THEMES[family] if t in have]
    raise ValueError(f"family '{family}' has no grouping definition")


def is_group_family(family: str) -> bool:
    """True for the five prompt_02 grouping families (2 methods each)."""
    return family in SECTOR_CLUSTERS or family in CRYPTO_THEMES


def fund_name(family: str, method: str) -> str:
    """Canonical fund id used in CSVs, e.g. 'equity_min_variance'."""
    return f"{family}_{method}"


def parse_fund_id(fund: str) -> tuple[str, str]:
    """Split a fund id into (family, method).

    Fund ids are '{family}_{method}'. Both sides can contain underscores
    ('min_variance' methods; 'growth_sensitive' family from prompt_02), so we
    infer the method as the KNOWN METHODS suffix and treat the leading slice
    as the family - a plain split("_", 1) breaks on underscore-bearing family
    ids (it would yield family='growth' for 'growth_sensitive_equal_weight').
    """
    for method in METHODS:
        if fund.endswith(f"_{method}"):
            family = fund[: -(len(method) + 1)]
            if family in FAMILIES:
                return family, method
    raise ValueError(f"unrecognised fund id '{fund}'")


def fund_display_name(family: str, method: str) -> str:
    """Human label, e.g. 'Equity Minimum-Variance'."""
    return f"{FAMILY_LABELS[family]} {METHOD_LABELS[method]}"


# ---------------------------------------------------------------------------
# Optimisers: each takes (mu, cov) -> weight vector
# ---------------------------------------------------------------------------

def _solve_long_only(objective, n: int, x0=None, jac=None):
    """Minimise `objective` under w >= 0, sum(w) = 1.

    Solver robustness (known trap: tiny daily-return covariances make SLSQP stall
    below tolerance): we solve on percent-scaled inputs, provide an analytic
    gradient where cheap, warm-start from a previous feasible point when given,
    and fall back to trust-constr before giving up.
    """
    if x0 is None:
        x0 = np.ones(n) / n
    x0 = np.asarray(x0, dtype=float)
    bounds = [(0.0, 1.0)] * n
    cons = {"type": "eq", "fun": lambda w: w.sum() - 1.0}
    kwargs = dict(bounds=bounds, constraints=cons, options={"maxiter": 2000, "disp": False})
    if jac is not None:
        kwargs["jac"] = jac
    res = minimize(objective, x0, method="SLSQP", **kwargs)
    if not res.success:
        # Fallback: trust-constr is generally more robust on badly scaled problems.
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = minimize(
                objective, x0, method="trust-constr",
                bounds=Bounds(0.0, 1.0), constraints=LinearConstraint(np.ones(n), 1.0, 1.0),
                options={"maxiter": 2000, "verbose": 0},
            )
    if not res.success:
        raise RuntimeError(f"optimiser failed to converge: {res.message}")
    return np.asarray(res.x)


def equal_weight(mu, cov, x0=None) -> np.ndarray:
    """w_i = 1/N. Ignores mu and cov entirely."""
    n = len(cov)
    return np.full(n, 1.0 / n)


def min_variance(mu, cov, x0=None) -> np.ndarray:
    """min_w w'Sigma w, long-only, sum(w)=1."""
    C = np.asarray(cov, dtype=float) * 10000.0  # percent-scale to avoid stall
    n = C.shape[0]

    def obj(w):
        return w @ C @ w

    def grad(w):
        return 2.0 * C @ w

    return _solve_long_only(obj, n, x0=x0, jac=grad)


def max_sharpe(mu, cov, x0=None) -> np.ndarray:
    """max_w (w'mu - rf) / sqrt(w'Sigma w), rf=0, long-only, sum(w)=1."""
    m = np.asarray(mu, dtype=float) * 100.0
    C = np.asarray(cov, dtype=float) * 10000.0
    n = C.shape[0]

    def obj(w):
        var = w @ C @ w
        if var <= 1e-16:
            return 0.0
        return -(m @ w) / np.sqrt(var)

    def grad(w):
        var = w @ C @ w
        s = np.sqrt(var)
        if s <= 1e-16:
            return np.zeros(n)
        # d/dw [ (m'w) / s ] = m/s - (m'w)(Cw)/s^3
        return -(m / s - (m @ w) * (C @ w) / (var * s))

    return _solve_long_only(obj, n, x0=x0, jac=grad)


def risk_parity(mu, cov, x0=None) -> np.ndarray:
    """Solve RC_i = w_i (Sigma w)_i / (w'Sigma w) = 1/N for all i.

    Minimises sum of squared deviations of risk contributions from 1/N.
    """
    C = np.asarray(cov, dtype=float) * 10000.0
    n = C.shape[0]
    target = 1.0 / n

    def rc(w):
        port_var = w @ C @ w
        return w * (C @ w) / port_var

    def obj(w):
        return np.sum((rc(w) - target) ** 2)

    w = _solve_long_only(obj, n, x0=x0)
    # verify risk contributions are close to equal
    contrib = rc(w)
    if np.max(np.abs(contrib - target)) > 0.02:
        raise RuntimeError(
            f"risk parity failed: risk contributions not equal "
            f"(max |RC-1/N| = {np.max(np.abs(contrib - target)):.4f})"
        )
    return w


def optimise(method: str, mu, cov, x0=None) -> np.ndarray:
    """Dispatch to the right optimiser and validate the output weights."""
    if method not in METHODS:
        raise ValueError(f"unknown method '{method}'; expected one of {METHODS}")
    w = {
        "equal_weight": equal_weight,
        "min_variance": min_variance,
        "max_sharpe": max_sharpe,
        "risk_parity": risk_parity,
    }[method](mu, cov, x0=x0)
    w = np.asarray(w, dtype=float)
    # Long-only, fully invested: clip tiny negatives, then renormalise so
    # sum(w) = 1 exactly holds at every rebalance.
    w = np.clip(w, 0.0, 1.0)
    s = w.sum()
    if s > 0:
        w = w / s
    assert np.all(w >= -WEIGHT_TOL), f"{method}: negative weight found"
    assert abs(w.sum() - 1.0) <= WEIGHT_TOL, f"{method}: weights do not sum to 1"
    return w


def assert_methods_differ(
    weight_vectors: dict[str, np.ndarray], tol: float = METHOD_DIFF_TOL
) -> None:
    """Sanity-check that all four methods give genuinely different weights.

    Known trap: optimisers on tiny daily-return covariances can silently stall
    below tolerance and collapse to near-identical weights. If any pair is closer
    than `tol`, raise rather than silently accept the collapsed solution.
    """
    names = list(weight_vectors.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            dist = np.max(np.abs(weight_vectors[names[i]] - weight_vectors[names[j]]))
            if dist <= tol:
                raise RuntimeError(
                    f"methods '{names[i]}' and '{names[j]}' collapsed to "
                    f"near-identical weights (max |diff| = {dist:.2e} <= {tol:.0e}) - "
                    f"solver likely stalled below tolerance; fix the scaling, "
                    f"do not silently accept it"
                )


# ---------------------------------------------------------------------------
# No-look-ahead guard
# ---------------------------------------------------------------------------

def assert_no_lookahead(hist_max_date, decision_date) -> None:
    """Raise if any data used to form a decision is dated on/after the decision."""
    if hist_max_date >= decision_date:
        raise AssertionError(
            f"look-ahead violation: estimation data extends to {hist_max_date}, "
            f"but the decision is made on {decision_date}"
        )


# ---------------------------------------------------------------------------
# Walk-forward out-of-sample backtest
# ---------------------------------------------------------------------------

def _monthly_rebalance_dates(dates: pd.DatetimeIndex, after: pd.Timestamp) -> list:
    """First trading day of each month, strictly after `after`."""
    s = pd.Series(dates, index=dates)
    first_of_month = (
        s.groupby([s.dt.year, s.dt.month]).first()
    )
    out = [d for d in first_of_month.tolist() if pd.Timestamp(d) > pd.Timestamp(after)]
    return sorted(pd.DatetimeIndex(out))


def oos_backtest(
    returns_wide: pd.DataFrame,
    method: str,
    initial_window: int = INITIAL_WINDOW_EQUITY,
    rebalance: str = "monthly",
) -> tuple[pd.Series, pd.DataFrame]:
    """Walk-forward expanding-window out-of-sample backtest for one method.

    Args:
        returns_wide: date x ticker daily simple returns (already computed within
            the universe's own calendar). Rows sorted ascending, no NaNs.
        method: one of METHODS.
        initial_window: number of daily return rows in the initial estimation
            window (a 'year' of that universe's calendar).
        rebalance: 'monthly' -> first trading day of each month.

    Returns:
        (portfolio_daily_returns, weights). portfolio_daily_returns is a Series of
        daily returns on the out-of-sample dates (indexed by date). weights is a
        DataFrame indexed by rebalance date with one column per ticker.

    No-look-ahead: at every rebalance date t, mu/Sigma are estimated from rows
    STRICTLY BEFORE t, and an assertion enforces it.
    """
    if rebalance != "monthly":
        raise ValueError(f"only 'monthly' rebalancing is supported, got '{rebalance}'")
    returns = returns_wide.sort_index().astype(float)
    # The optimisers scale to percent internally (see min_variance/max_sharpe);
    # here we estimate mu/Sigma on decimal returns and pass them through.
    dates = returns.index

    if len(dates) <= initial_window:
        raise ValueError(
            f"panel has {len(dates)} rows but initial_window needs {initial_window}"
        )

    window_end = dates[initial_window - 1]
    rebal_dates = _monthly_rebalance_dates(dates, after=window_end)
    if not rebal_dates:
        raise ValueError("no rebalance dates after the initial estimation window")

    weights_rows = []
    warm = None  # warm-start the solver from the previous rebalance's weights
    for t in rebal_dates:
        hist = returns.loc[returns.index < t]
        assert_no_lookahead(hist.index.max(), t)
        mu = hist.mean()
        cov = hist.cov()
        w = optimise(method, mu, cov, x0=warm)
        warm = w
        weights_rows.append(pd.Series(w, index=returns.columns, name=t))
    weights = pd.DataFrame(weights_rows)
    weights.index.name = "date"

    # Portfolio daily returns on all out-of-sample dates.
    oos_mask = returns.index > window_end
    oos_dates = returns.index[oos_mask]

    # For each OOS day, the weight vector in force = last rebalance <= that day.
    rebal_idx = pd.Index(rebal_dates)
    pos = rebal_idx.searchsorted(oos_dates, side="right") - 1
    w_matrix = weights.to_numpy()[pos]  # n_oos x n_assets

    daily = returns.loc[oos_dates]
    assert not daily.isna().any().any(), "NaN return present in the OOS window"

    port = (w_matrix * daily.to_numpy()).sum(axis=1)
    port_returns = pd.Series(port, index=oos_dates, name=fund_name("", method))
    return port_returns, weights


def backtest_all_methods(
    returns_wide: pd.DataFrame,
    family: str,
    ann_factor: int,
    initial_window: int,
    methods: list[str] | None = None,
) -> dict[str, tuple[pd.Series, pd.DataFrame]]:
    """Run a family's methods for one universe and sanity-check they differ.

    `methods` defaults to all four; the prompt_02 grouping families pass
    GROUP_METHODS (equal-weight + risk parity only). Returns {fund_id:
    (daily_returns, weights)}. At every common rebalance date, asserts the
    weight vectors are pairwise distinct (catches solver stall). Single-method
    families are still validated individually inside oos_backtest.
    """
    methods = methods or METHODS
    results = {}
    for m in methods:
        ret, w = oos_backtest(returns_wide, m, initial_window=initial_window)
        results[fund_name(family, m)] = (ret, w)

    if len(methods) > 1:
        weight_by_method = {m: results[fund_name(family, m)][1] for m in methods}
        common_dates = weight_by_method[methods[0]].index
        for d in common_dates:
            ws = {m: weight_by_method[m].loc[d].to_numpy() for m in methods}
            assert_methods_differ(ws)
    return results


# ---------------------------------------------------------------------------
# Performance metrics
# ---------------------------------------------------------------------------

def performance_metrics(daily_returns: pd.Series, ann_factor: int) -> dict:
    """Annualised return, volatility, Sharpe (rf=0), max drawdown, total return."""
    r = daily_returns.dropna()
    if len(r) == 0:
        return {"annualised_return": np.nan, "annualised_volatility": np.nan,
                "sharpe_ratio": np.nan, "max_drawdown": np.nan, "total_return": np.nan}
    ann_ret = float(r.mean() * ann_factor)
    ann_vol = float(r.std(ddof=1) * np.sqrt(ann_factor))
    sharpe = ann_ret / ann_vol if ann_vol > 0 else np.nan
    cum = (1.0 + r).cumprod()
    running_max = cum.cummax()
    dd = cum / running_max - 1.0
    max_dd = float(dd.min())
    total = float(cum.iloc[-1] - 1.0)
    return {
        "annualised_return": ann_ret,
        "annualised_volatility": ann_vol,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_dd,
        "total_return": total,
    }


def turnover(weights: pd.DataFrame) -> float:
    """Mean absolute weight change at each rebalance (first rebalance from 0)."""
    if weights.shape[0] == 0:
        return 0.0
    moves = []
    prev = np.zeros(weights.shape[1])
    for _, row in weights.iterrows():
        w = row.to_numpy(dtype=float)
        moves.append(float(np.abs(w - prev).sum()))
        prev = w
    return float(np.mean(moves))


def build_metrics_table(
    fund_results: dict[str, tuple[pd.Series, pd.DataFrame]],
    ann_factors: dict[str, int],
) -> pd.DataFrame:
    """Performance-metrics table across all funds (core 12 + grouping 10).

    fund_results maps fund id -> (daily_returns, weights).
    """
    rows = []
    for fund, (ret, w) in fund_results.items():
        family, method = parse_fund_id(fund)
        ann = ann_factors[family]
        m = performance_metrics(ret, ann)
        m["fund"] = fund
        m["family"] = family
        m["method"] = method
        m["turnover"] = turnover(w)
        m["first_live_date"] = ret.index.min().strftime("%Y-%m-%d")
        m["last_date"] = ret.index.max().strftime("%Y-%m-%d")
        rows.append(m)
    cols = ["fund", "family", "method", "annualised_return", "annualised_volatility",
            "sharpe_ratio", "max_drawdown", "total_return", "turnover",
            "first_live_date", "last_date"]
    return pd.DataFrame(rows).sort_values("fund").reset_index(drop=True)[cols]
