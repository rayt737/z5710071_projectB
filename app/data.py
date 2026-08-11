"""Station 4 app data layer - reads precomputed results only.

Pure pandas over the committed CSVs under ``results/``. The app is not allowed
to import or run any Station 3 model (no backtest, no optimiser, no sentiment
scorer); everything a user sees is a direct read or a simple pandas aggregation
of an already-computed column. See ai/prompts/prompt_04.md and the project
AGENTS.md traceability rule. Nothing here imports streamlit, so the pure
functions are unit-testable without a browser.
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

METRIC_COLS = [
    "annualised_return",
    "annualised_volatility",
    "sharpe_ratio",
    "max_drawdown",
]

UNIVERSES = ("Equity", "Crypto", "Multi-Asset")

# family (as recorded in performance_metrics.csv) -> universe
FAMILY_UNIVERSE = {
    "equity": "Equity",
    "defensive": "Equity",
    "cyclical": "Equity",
    "growth_sensitive": "Equity",
    "crypto": "Crypto",
    "payments": "Crypto",
    "web3infra": "Crypto",
    "combined": "Multi-Asset",
}

# stable display order within each universe (composition per prompt_04)
METHOD_ORDER = ["equal_weight", "min_variance", "max_sharpe", "risk_parity"]
FAMILY_ORDER = {
    "Equity": ["equity", "defensive", "cyclical", "growth_sensitive"],
    "Crypto": ["crypto", "payments", "web3infra"],
    "Multi-Asset": ["combined"],
}

FUSION_VARIANTS = ["equity_min_variance_momentum", "equity_min_variance_contrarian"]
FUSION_SUFFIXES = ("_momentum", "_contrarian")
VOL_TARGET_SUFFIX = "_vol_targeted"


def _path(*parts: str) -> pathlib.Path:
    return RESULTS.joinpath(*parts)


def required_files() -> list[pathlib.Path]:
    return [
        _path("data", "fund_returns.csv"),
        _path("data", "fund_weights.csv"),
        _path("data", "sector_sentiment_index.csv"),
        _path("data", "fund_display_names.csv"),
        _path("data", "fund_fees.csv"),
        _path("tables", "performance_metrics.csv"),
        _path("tables", "fusion_comparison.csv"),
        _path("tables", "vol_target_comparison.csv"),
    ]


def check_results() -> None:
    missing = [str(p) for p in required_files() if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "missing results files: " + "; ".join(missing)
            + ". Reproduce the data first with: python scripts/run_part_b.py"
        )


def load_display_names() -> pd.DataFrame:
    return pd.read_csv(_path("data", "fund_display_names.csv"))


def load_fund_fees() -> pd.DataFrame:
    return pd.read_csv(_path("data", "fund_fees.csv"))


def load_fund_returns() -> pd.DataFrame:
    return pd.read_csv(_path("data", "fund_returns.csv"), parse_dates=["date"])


def load_fund_weights() -> pd.DataFrame:
    return pd.read_csv(_path("data", "fund_weights.csv"), parse_dates=["rebalance_date"])


def load_sector_sentiment() -> pd.DataFrame:
    return pd.read_csv(_path("data", "sector_sentiment_index.csv"), parse_dates=["date"])


def load_performance_metrics() -> pd.DataFrame:
    return pd.read_csv(_path("tables", "performance_metrics.csv"))


def load_fusion_comparison() -> pd.DataFrame:
    return pd.read_csv(_path("tables", "fusion_comparison.csv"))


def load_vol_target_comparison() -> pd.DataFrame:
    return pd.read_csv(_path("tables", "vol_target_comparison.csv"))


def _family_map(metrics: pd.DataFrame) -> dict[str, str]:
    return dict(zip(metrics["fund"], metrics["family"]))


def universe_funds(
    metrics: pd.DataFrame, fusion: pd.DataFrame, vol_target: pd.DataFrame
) -> dict[str, list[str]]:
    """Ordered fund-id lists per universe (Equity 12 / Crypto 9 / Multi-Asset 5).

    Derived from the data, not a hardcoded fund list: base funds come from
    performance_metrics.csv by family; fusion variants (momentum/contrarian) are
    always equity and come from fusion_comparison.csv; vol-targeted variants
    inherit the universe of their base fund (vol_target_comparison.csv +
    performance_metrics.csv). The ``{base}_base`` rows in the comparison CSVs
    are excluded - they duplicate a core fund.
    """
    fam_map = _family_map(metrics)
    funds: dict[str, list[str]] = {u: [] for u in UNIVERSES}
    for fund, family in fam_map.items():
        universe = FAMILY_UNIVERSE.get(family)
        if universe is not None:
            funds[universe].append(fund)
    funds["Equity"].extend(
        f for f in fusion["fund"] if f.endswith(FUSION_SUFFIXES)
    )
    for f in vol_target["fund"]:
        if not f.endswith(VOL_TARGET_SUFFIX):
            continue
        base = f[: -len(VOL_TARGET_SUFFIX)]
        universe = FAMILY_UNIVERSE.get(fam_map.get(base))
        if universe is not None:
            funds[universe].append(f)
    return {u: _sort_funds(u, funds[u], fam_map) for u in UNIVERSES}


def _variant_rank(fund: str) -> tuple[int, int]:
    if fund in FUSION_VARIANTS:
        return (0, FUSION_VARIANTS.index(fund))
    base = fund[: -len(VOL_TARGET_SUFFIX)]
    return (1, {"combined_max_sharpe": 0, "crypto_max_sharpe": 1}.get(base, 9))


def _sort_funds(
    universe: str, fund_ids: list[str], fam_map: dict[str, str]
) -> list[str]:
    family_rank = {f: i for i, f in enumerate(FAMILY_ORDER[universe])}
    method_rank = {m: i for i, m in enumerate(METHOD_ORDER)}
    core, variants = [], []
    for fund in fund_ids:
        (variants if fund not in fam_map else core).append(fund)
    core.sort(
        key=lambda f: (
            family_rank.get(fam_map[f], 99),
            method_rank.get(f[len(fam_map[f]) + 1:], 99),
        )
    )
    variants.sort(key=_variant_rank)
    return core + variants


def fund_type(fund: str, fam_map: dict[str, str]) -> str:
    if fund.endswith(FUSION_SUFFIXES):
        return "Fusion variant"
    if fund.endswith(VOL_TARGET_SUFFIX):
        return "Vol-targeted"
    family = fam_map.get(fund)
    if family in ("equity", "crypto", "combined"):
        return "Core"
    if family in ("defensive", "cyclical", "growth_sensitive"):
        return "Sector cluster"
    if family in ("payments", "web3infra"):
        return "Crypto theme"
    return "Other"


def unified_metrics(
    metrics: pd.DataFrame, fusion: pd.DataFrame, vol_target: pd.DataFrame
) -> pd.DataFrame:
    """One row per fund id with the four headline numbers + source CSV."""
    parts = []
    for frame, source in (
        (metrics, "results/tables/performance_metrics.csv"),
        (fusion, "results/tables/fusion_comparison.csv"),
        (vol_target, "results/tables/vol_target_comparison.csv"),
    ):
        part = frame[["fund", *METRIC_COLS]].copy()
        part["source"] = source
        parts.append(part)
    return pd.concat(parts, ignore_index=True).drop_duplicates("fund").reset_index(drop=True)


def fund_return_series(returns: pd.DataFrame, fund: str) -> pd.Series:
    sub = returns.loc[returns["fund"] == fund, ["date", "return"]]
    return sub.set_index("date")["return"].sort_index()


def growth_of_1(series: pd.Series) -> pd.Series:
    return (1 + series).cumprod()


def drawdown_from_returns(series: pd.Series) -> pd.Series:
    growth = growth_of_1(series)
    return growth / growth.cummax() - 1.0


def base_fund_of(fund: str) -> str:
    """The base fund a variant is built on (identity for non-vol-target funds)."""
    if fund.endswith(VOL_TARGET_SUFFIX):
        return fund[: -len(VOL_TARGET_SUFFIX)]
    return fund


def latest_holdings(weights: pd.DataFrame, fund: str) -> tuple[pd.DataFrame, object]:
    """Top-down weights at the fund's most recent rebalance date."""
    sub = weights.loc[weights["fund"] == fund]
    if sub.empty:
        return pd.DataFrame(columns=["ticker", "weight"]), None
    latest = sub["rebalance_date"].max()
    out = (
        sub.loc[sub["rebalance_date"] == latest, ["ticker", "weight"]]
        .sort_values("weight", ascending=False)
        .reset_index(drop=True)
    )
    return out, latest


def blend_portfolio(
    returns: pd.DataFrame,
    funds: list[str],
    weights: dict[str, float],
    fee_annual: float,
) -> pd.DataFrame:
    """Daily gross / net growth of a normalised weight blend.

    Fund daily returns are aligned on the union of their calendars; a date a
    fund has no row for (market closed) counts as a 0% return. The management
    fee is charged daily on AUM at ``fee_annual / 365``.
    """
    sub = returns.loc[returns["fund"].isin(funds)]
    wide = sub.pivot(index="date", columns="fund", values="return").sort_index().fillna(0.0)
    w = pd.Series({f: weights[f] for f in funds})
    r = wide.dot(w)
    gross = (1 + r).cumprod()
    net = ((1 + r) * (1 - fee_annual / 365.0)).cumprod()
    return pd.DataFrame({"gross": gross, "net": net})


def blended_fee(weights: dict[str, float], fees: dict[str, float]) -> float:
    """Weighted-average annual management fee of a normalised weight blend.

    ``blended_fee = sum(weight_i * fee_i)`` over the user's actual selection
    (prompt_06 item 6) - the single ``fee_annual`` passed to blend_portfolio.
    """
    return sum(w * fees[fund] for fund, w in weights.items())


def annualisation_factor(index: pd.DatetimeIndex) -> float:
    """Empirical days-per-year of a series, from its own observed calendar.

    ``len(index) / (calendar span in years)``. A pure equity series is ~252;
    a blend that includes crypto funds trades on the date-union of both
    calendars (crypto adds weekend/holiday rows equity has none for), so its
    true frequency sits between 252 and 365 depending on weight - a flat
    sqrt(252) would silently understate its annualised vol and return. The
    factor is therefore derived per-series from real data, never assumed
    (same calendar-mismatch rule the project applies everywhere else).
    """
    span_days = max(int((index[-1] - index[0]).days), 1)
    years = span_days / 365.25
    return float(len(index) / years)


def portfolio_metrics(growth: pd.DataFrame) -> dict[str, float]:
    """The four headline metrics computed on a blended growth series.

    Daily returns are recovered from the gross growth column
    (``gross_t / gross_{t-1} - 1``). The annualisation factor is derived
    empirically from the blend's own date-union calendar (annualisation_factor)
    rather than hardcoded at equity's 252 - crypto-inclusive blends genuinely
    trade closer to 365 days/year. rf = 0, Sharpe = ann_return / ann_vol.
    """
    gross = growth["gross"]
    r = gross.pct_change().dropna()
    ann = annualisation_factor(gross.index)
    ann_ret = float(r.mean() * ann)
    ann_vol = float(r.std(ddof=1) * (ann ** 0.5))
    sharpe = ann_ret / ann_vol if ann_vol > 0 else float("nan")
    dd = (gross / gross.cummax() - 1.0).min()
    return {
        "annualised_return": ann_ret,
        "annualised_volatility": ann_vol,
        "sharpe_ratio": sharpe,
        "max_drawdown": float(dd),
        "total_return": float(gross.iloc[-1] - 1.0),
        "annualisation_factor": ann,
    }


def market_sentiment_series(sector: pd.DataFrame) -> pd.Series:
    """Equal-weighted market-wide sector sentiment (display column)."""
    return sector.groupby("date")["sentiment_aligned"].mean().sort_index()


def rescale_0_100(series: pd.Series) -> pd.Series:
    lo, hi = float(series.min()), float(series.max())
    if hi <= lo:
        return pd.Series(50.0, index=series.index)
    return (series - lo) / (hi - lo) * 100.0


def wrap_label(name: str, width: int = 22) -> str:
    """Wrap a display name at word boundaries; join with <br> for Plotly ticks."""
    lines, cur = [], ""
    for word in name.split():
        if cur and len(cur) + 1 + len(word) <= width:
            cur = f"{cur} {word}"
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return "<br>".join(lines)


@dataclass
class AppData:
    lookup: dict[str, str]
    universe_funds: dict[str, list[str]]
    metrics: pd.DataFrame
    returns: pd.DataFrame
    weights: pd.DataFrame
    sector: pd.DataFrame
    sectors: list[str]
    allocation_funds: list[str]
    unclassified: list[str]
    fees: dict[str, float]
    market_sentiment: pd.Series


def build_app_data() -> AppData:
    check_results()
    display = load_display_names()
    lookup = dict(zip(display["fund_id"], display["display_name"]))
    fees = dict(zip(load_fund_fees()["fund_id"], load_fund_fees()["fee_annual"]))
    metrics = load_performance_metrics()
    fusion = load_fusion_comparison()
    vol_target = load_vol_target_comparison()
    returns = load_fund_returns()
    weights = load_fund_weights()
    sector = load_sector_sentiment()

    fam_map = _family_map(metrics)
    funds = universe_funds(metrics, fusion, vol_target)
    unified = unified_metrics(metrics, fusion, vol_target)

    rows = []
    for universe in UNIVERSES:
        for fund in funds[universe]:
            m = unified.loc[unified["fund"] == fund].iloc[0]
            row = {
                "fund": fund,
                "display_name": lookup[fund],
                "type": fund_type(fund, fam_map),
                "universe": universe,
                "source": m["source"],
            }
            for col in METRIC_COLS:
                row[col] = m[col]
            rows.append(row)
    app_metrics = pd.DataFrame(rows)

    return_ids = set(returns["fund"])
    # Every universe fund now has a published return series (prompt_05 appended
    # the 4 variant series), so the allocation picker is exactly the 26 universe
    # funds. The filter is kept as a safety net against a stale results/ dir.
    allocation_funds = [
        f for u in UNIVERSES for f in funds[u] if f in return_ids
    ]

    all_ids = (
        set(metrics["fund"])
        | set(fusion["fund"])
        | set(vol_target["fund"])
        | set(returns["fund"])
        | set(weights["fund"])
    )
    universe_ids = {f for u in funds.values() for f in u}
    base_rows = {f for f in all_ids if f.endswith("_base")}
    unclassified = sorted(all_ids - universe_ids - base_rows)

    return AppData(
        lookup=lookup,
        universe_funds=funds,
        metrics=app_metrics,
        returns=returns,
        weights=weights,
        sector=sector,
        sectors=sorted(sector["sector"].unique()),
        allocation_funds=allocation_funds,
        unclassified=unclassified,
        fees=fees,
        market_sentiment=market_sentiment_series(sector),
    )
