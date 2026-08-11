"""Station 3 - reproduce every Part B fund / sentiment / fusion output.

Run from the project root:

    python scripts/run_part_b.py

Pipeline: load data -> 22 funds (12 core + 10 prompt_02 groupings, walk-forward
OOS backtest) -> metrics -> vol-targeting overlay -> sentiment (VADER +
finVADER-lite) -> sector index -> fusion baseline -> save every CSV/table/figure
required by ai/prompts/prompt_01.md, prompt_02.md and prompt_05.md, then print
a console summary of all 22 Sharpe ratios, the new grouping funds, the fusion
comparison and the vol-targeting comparison.

fund_returns.csv / fund_weights.csv additionally carry the 4 extension-variant
series appended in save_funds_and_metrics (prompt_05): the 2 fusion tilts and
the 2 vol-targeted overlays (returns), and the 2 fusion tilt weight series
(weights - the vol-targeted variants inherit their base fund's holdings).

Every number in the report must trace to one of the CSVs written here:
  results/data/fund_returns.csv
  results/data/fund_weights.csv
  results/data/sector_sentiment_index.csv
  results/data/headline_sentiment.csv
  results/tables/performance_metrics.csv
  results/tables/fusion_comparison.csv
  results/tables/vol_target_comparison.csv
"""
from __future__ import annotations

import pathlib
import sys
import time

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import branding as brand  # noqa: E402
from src import etl, features, plots  # noqa: E402
from src import fusion as fu  # noqa: E402
from src import portfolios as pf  # noqa: E402
from src import sentiment as sent  # noqa: E402
from src import vol_target as vt  # noqa: E402


def _t(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def save_csv(df: pd.DataFrame, rel: str) -> pathlib.Path:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    _t(f"wrote {rel} ({df.shape[0]} rows)")
    return path


def load_panels() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load prices, build the wide panels, return (eq, cr, eq_wide, cr_wide, combined_wide)."""
    eq, _ = etl.load_clean_equities()
    cr, _ = etl.load_clean_crypto()
    eq_wide = features.returns_to_wide(eq).dropna(how="all")
    cr_wide = features.returns_to_wide(cr).dropna(how="all")
    combined_wide = etl.build_combined_returns_panel(eq, cr).set_index("date").dropna(how="all")
    _t(f"equity panel {eq_wide.shape}, crypto panel {cr_wide.shape}, "
       f"combined panel {combined_wide.shape}")
    return eq, cr, eq_wide, cr_wide, combined_wide


def _backtest_family(fund_results, family, panel, methods=None):
    """Backtest one family into fund_results, logging each fund's OOS span."""
    _t(f"backtesting {family} ({panel.shape[1]} assets, {panel.shape[0]} days)...")
    results = pf.backtest_all_methods(
        panel, family, pf.ANNUAL_FACTORS[family], pf.INITIAL_WINDOWS[family],
        methods=methods)
    fund_results.update(results)
    for fund_id, (ret, _w) in results.items():
        _t(f"  {fund_id}: {len(ret)} OOS days, first live {ret.index.min().date()}")
    return fund_results


def backtest_funds(eq, cr, eq_wide, cr_wide,
                   combined_wide) -> dict[str, tuple[pd.Series, pd.DataFrame]]:
    """Walk-forward OOS backtest across all 22 funds, with method-difference checks."""
    panels = {"equity": eq_wide, "crypto": cr_wide, "combined": combined_wide}
    fund_results: dict[str, tuple[pd.Series, pd.DataFrame]] = {}
    for family in ["equity", "crypto", "combined"]:
        fund_results = _backtest_family(fund_results, family, panels[family])

    # prompt_02: five new grouping families, equal-weight + risk parity only.
    # Sector clusters derive their tickers from the data's `sector` column;
    # crypto themes use the explicit ticker lists in portfolios.CRYPTO_THEMES.
    for family in pf.SECTOR_CLUSTERS:
        tickers = pf.group_universe_tickers(eq, cr, family)
        panel = eq_wide[[t for t in tickers if t in eq_wide.columns]].dropna(how="all")
        fund_results = _backtest_family(fund_results, family, panel, methods=pf.GROUP_METHODS)
    for family in pf.CRYPTO_THEMES:
        tickers = pf.group_universe_tickers(eq, cr, family)
        panel = cr_wide[[t for t in tickers if t in cr_wide.columns]].dropna(how="all")
        fund_results = _backtest_family(fund_results, family, panel, methods=pf.GROUP_METHODS)
    return fund_results


def _returns_long(series: pd.Series, fund: str) -> pd.DataFrame:
    return pd.DataFrame({"date": series.index, "fund": fund, "return": series.values})


def _weights_long(weights: pd.DataFrame, fund: str) -> pd.DataFrame:
    w = weights.reset_index()
    w = w.melt(id_vars=w.columns[0], var_name="ticker", value_name="weight")
    w = w.rename(columns={w.columns[0]: "rebalance_date"})
    w["fund"] = fund
    return w[["fund", "rebalance_date", "ticker", "weight"]]


def save_funds_and_metrics(fund_results, fusion_parts, vt_parts) -> pd.DataFrame:
    """Write fund_returns.csv / fund_weights.csv / performance_metrics.csv.

    fund_returns.csv carries the 22 base funds PLUS the 4 extension variants:
    the 2 fusion tilts (daily returns on the equity calendar) and the 2
    vol-targeted overlays (scaled returns on their base fund's OOS calendar).
    fund_weights.csv carries the 22 base funds PLUS the 2 fusion tilt weight
    series (same monthly rebalance dates as the base fund - the tilt is
    recomputed at each rebalance). The vol-targeted variants get NO weight
    rows: the overlay is a portfolio-level scalar (k_t), so their holdings are
    the base fund's - handled by the app, not duplicated here (prompt_05).
    """
    ret_parts = [_returns_long(ret, fund) for fund, (ret, _w) in sorted(fund_results.items())]
    w_parts = [_weights_long(w, fund) for fund, (_ret, w) in sorted(fund_results.items())]

    _, _, momentum, contrarian, _ = fusion_parts
    for label, (ret, w) in [("momentum", momentum), ("contrarian", contrarian)]:
        fund = f"equity_min_variance_{label}"
        ret_parts.append(_returns_long(ret, fund))
        w_parts.append(_weights_long(w, fund))

    for label in ["combined_max_sharpe", "crypto_max_sharpe"]:
        fund = f"{label}_vol_targeted"
        ret_parts.append(_returns_long(vt_parts[label][1], fund))

    save_csv(pd.concat(ret_parts, ignore_index=True), "results/data/fund_returns.csv")
    save_csv(pd.concat(w_parts, ignore_index=True), "results/data/fund_weights.csv")

    metrics = pf.build_metrics_table(fund_results, pf.ANNUAL_FACTORS)
    save_csv(metrics, "results/tables/performance_metrics.csv")
    return metrics


def save_display_names() -> None:
    """Write the investor-facing fund-id -> display-name lookup for Station 4."""
    save_csv(brand.display_names_table(), "results/data/fund_display_names.csv")


def save_fund_fees() -> None:
    """Write the fixed per-fund management-fee schedule for Station 4.

    The app must not import src.branding, so the fee schedule travels via a CSV
    exactly like fund_display_names.csv (prompt_06 item 6).
    """
    save_csv(brand.fees_table(), "results/data/fund_fees.csv")


def save_sentiment_summary(merged: pd.DataFrame) -> None:
    """Precompute the aggregated VADER-vs-finVADER summary the app renders.

    The app must never load the full 146,836-row headline_sentiment.csv
    (prompt_06 item 5 - that is why this used to be a static image), so the
    pipeline writes one small long-format CSV carrying everything the app's
    native chart needs to reproduce the Station 3 comparison:
      - monthly_mean rows: mean compound per lexicon per calendar month
      - histogram rows: 60-bin density-reproducible counts per lexicon
        (np.linspace(-1, 1, 61) edges - the same bins as
        src/plots.fig_sentiment_comparison)
      - neutral row: fraction of finVADER-lite headlines with |c| < 0.05
    """
    rows = []
    monthly = (merged.assign(ym=merged["date"].dt.to_period("M"))
               .groupby("ym")[["plain_vader", "finvader_lite"]].mean().reset_index())
    for lexicon in ["plain_vader", "finvader_lite"]:
        for _, r in monthly.iterrows():
            if pd.isna(r[lexicon]):
                continue
            rows.append({"series": "monthly_mean", "date": r["ym"].to_timestamp(),
                         "bin_start": float("nan"), "lexicon": lexicon,
                         "value": float(r[lexicon])})

    bins = np.linspace(-1, 1, 61)
    for lexicon in ["plain_vader", "finvader_lite"]:
        counts, _ = np.histogram(merged[lexicon].dropna(), bins=bins)
        for left, c in zip(bins[:-1], counts):
            rows.append({"series": "histogram", "date": pd.NaT, "bin_start": float(left),
                         "lexicon": lexicon, "value": float(c)})

    rows.append({"series": "neutral", "date": pd.NaT, "bin_start": float("nan"),
                 "lexicon": "finvader_lite",
                 "value": float((merged["finvader_lite"].abs() < 0.05).mean())})
    summary = pd.DataFrame(rows)
    save_csv(summary, "results/data/sentiment_lexicon_comparison_summary.csv")
    _t(f"sentiment summary: {monthly.shape[0]} months, 60-bin histogram per lexicon")


def build_sentiment(eq: pd.DataFrame):
    """Score all headlines twice (plain VADER + finVADER-lite), build the sector index.

    Returns (headline_sentiment, aligned, lagged, sector_index_long).
    """
    nl, _ = etl.load_clean_headlines()
    sector_map = dict(zip(eq["ticker"], eq["sector"]))
    eq_dates = pd.DatetimeIndex(sorted(eq["date"].unique()))

    panel = features.assemble_headline_panel(nl, eq_dates, tz_aware=True)
    _t(f"headlines assembled: {len(panel)} rows on the equity calendar")

    plain = sent.build_plain_vader()
    extended = sent.build_finvader_lite()
    _t("scoring headlines with plain VADER...")
    plain_scores = sent.score_headlines(panel, plain)
    _t("scoring headlines with finVADER-lite...")
    ext_scores = sent.score_headlines(panel, extended)

    merged = plain_scores.rename(columns={"compound": "plain_vader"})
    merged["finvader_lite"] = ext_scores["compound"]
    merged = merged[["date", "ticker", "sector", "title", "url", "publisher",
                     "plain_vader", "finvader_lite"]]
    save_csv(merged, "results/data/headline_sentiment.csv")

    index_long, aligned, lagged = sent.build_sector_sentiment_index(
        ext_scores, eq_dates, sector_map)
    save_csv(index_long, "results/data/sector_sentiment_index.csv")
    save_sentiment_summary(merged)
    _t(f"sector index: {index_long['sector'].nunique()} sectors, "
       f"{index_long['date'].nunique()} trading days")
    return merged, aligned, lagged, index_long


def build_fusion(fund_results, eq_wide, aligned):
    """Fusion tilt on the equity min-variance base, both lambda settings."""
    base_ret, base_w = fund_results["equity_min_variance"]
    _t("running fusion tilts on the equity min-variance base (lambda +1 / -1)...")
    momentum = fu.run_fusion(eq_wide, base_w, aligned, +1.0)
    contrarian = fu.run_fusion(eq_wide, base_w, aligned, -1.0)
    table = fu.build_fusion_comparison(base_ret, base_w, {
        "momentum": momentum, "contrarian": contrarian}, ann_factor=252)
    save_csv(table, "results/tables/fusion_comparison.csv")
    return base_ret, base_w, momentum, contrarian, table


def build_full_history(panel, base_returns, weights) -> pd.Series:
    """Pre-live returns of a fund + its out-of-sample returns (the full history).

    The pre-live segment = the fund's first-rebalance weights applied to the
    estimation-window asset returns - the same data that set those weights, so
    it is fully known before live trading starts. Concatenating it with the OOS
    returns lets the vol-target overlay use a causal trailing window from day 1
    of live trading, and lets the target be the initial-window vol (no
    look-ahead; see ai/prompt_log.md Entry 7).
    """
    live_start = base_returns.index[0]
    est = panel.loc[panel.index < live_start]
    first_w = weights.iloc[0]
    pre = est.mul(first_w, axis=1).sum(axis=1)
    pre.index.name = None
    return pd.concat([pre, base_returns])


def build_vol_target(fund_results, panels):
    """Volatility-targeting overlay on Combined Max-Sharpe (+ Crypto Max-Sharpe).

    Target vol = annualised realised vol over the fund's INITIAL ESTIMATION
    WINDOW only (252 equity/combined, 365 crypto) - the same pre-live window
    that set the fund's first weights, fixed once and never recomputed, so the
    target carries no out-of-sample information. The overlay runs on the fund's
    full history (pre-live implied returns + OOS returns, see
    `build_full_history`); outputs are sliced back to the OOS period. Otherwise
    k_t = target / 60-day trailing realised vol, clipped to [0.5, 1.5]
    (see src/vol_target.py).
    """
    labels = ["combined_max_sharpe", "crypto_max_sharpe"]
    _t("running vol-targeting overlays on " + ", ".join(labels) + "...")
    parts = {}
    targets = {}
    for label in labels:
        base, weights = fund_results[label]
        family = pf.parse_fund_id(label)[0]
        ann = pf.ANNUAL_FACTORS[family]
        init = pf.INITIAL_WINDOWS[family]
        full = build_full_history(panels[family], base, weights)
        scaled_full, k_full, target = vt.apply_overlay(full, ann, init)
        scaled = scaled_full.loc[base.index]
        k = k_full.loc[base.index]
        parts[label] = (base, scaled, k)
        targets[label] = target
        _t(f"  {label}: target_vol {target:.4f} (initial window {init}d, "
           f"{full.index[0].date()}..{full.index[init - 1].date()}), "
           f"k in [{k.min():.3f}, {k.max():.3f}]")
    table = vt.build_vol_target_comparison(
        {label: (base, scaled) for label, (base, scaled, _k) in parts.items()},
        pf.ANNUAL_FACTORS, targets)
    save_csv(table, "results/tables/vol_target_comparison.csv")
    return parts, table


def make_figures(fund_results, metrics, merged, index_long, fusion_parts, eq, vt_parts):
    base_ret, _base_w, momentum, contrarian, _ = fusion_parts

    # 1. Performance-metrics table
    plots.fig_metrics_table(metrics)

    # 2. Growth of $1 per universe
    ret_long = pd.concat([
        pd.DataFrame({"date": ret.index, "fund": fund, "return": ret.values})
        for fund, (ret, _w) in sorted(fund_results.items())
    ], ignore_index=True)
    plots.fig_growth_of_1(ret_long, "equity", "growth_of_1_equity.png")
    plots.fig_growth_of_1(ret_long, "crypto", "growth_of_1_crypto.png")
    plots.fig_growth_of_1(ret_long, "combined", "growth_of_1_combined.png")

    # 3. Drawdown of the combined max-Sharpe fund (most concentrated/volatile)
    cms_ret = fund_results["combined_max_sharpe"][0]
    plots.fig_drawdown(cms_ret, brand.fund_display_name("combined_max_sharpe"),
                       "drawdown_combined_max_sharpe.png", fund_id="combined_max_sharpe")

    # 4. Weights over time: combined min-variance, by sector (+ crypto band)
    w = fund_results["combined_min_variance"][1]
    sector_map = dict(zip(eq["ticker"], eq["sector"]))
    plots.fig_weights_stacked(w, sector_map, brand.fund_display_name("combined_min_variance"),
                              "portfolio_weights_combined_min_variance.png",
                              fund_id="combined_min_variance")

    # 5. Sharpe barplot across all 22 funds
    plots.fig_sharpe_barplot(metrics)

    # 6. Sentiment before/after (plain VADER vs finVADER-lite)
    plain_s = merged.set_index("date")["plain_vader"].sort_index()
    ext_s = merged.set_index("date")["finvader_lite"].sort_index()
    plots.fig_sentiment_comparison(plain_s, ext_s)

    # 7. Sector sentiment index over time
    plots.fig_sector_sentiment(index_long)

    # 8. Fusion before/after growth of $1
    plots.fig_fusion_growth(base_ret, momentum[0], contrarian[0])

    # 9. New groupings (prompt_02): growth of $1 per asset-class theme
    plots.fig_growth_groupings(
        ret_long, ["defensive", "cyclical", "growth_sensitive"],
        "growth_of_1_sector_clusters.png",
        "Equity sector-cluster funds (Defensive / Cyclical / Growth-Sensitive) — growth of $1")
    plots.fig_growth_groupings(
        ret_long, ["payments", "web3infra"],
        "growth_of_1_crypto_themes.png",
        "Crypto thematic funds (Payment / Web3 Infrastructure) — growth of $1")

    # 10. Vol-targeting overlay figures (base vs targeted + k_t scaling factor)
    for label, suffix in [
        ("combined_max_sharpe", "combined_max_sharpe"),
        ("crypto_max_sharpe", "crypto_max_sharpe"),
    ]:
        base, scaled, k = vt_parts[label]
        plots.fig_vol_target_growth(
            base, scaled, brand.fund_display_name(label),
            f"growth_vol_target_{suffix}.png",
            managed_label=brand.VOL_TARGET_DISPLAY_NAMES[label], fund_id=label)
        plots.fig_vol_target_scaling(
            k, brand.VOL_TARGET_DISPLAY_NAMES[label],
            f"vol_target_scaling_{suffix}.png")

    _t("all figures written to results/figures/")


def _fmt_metric_table(df: pd.DataFrame, cols) -> pd.DataFrame:
    show = df[cols].copy()
    show["sharpe_ratio"] = show["sharpe_ratio"].round(3)
    show["annualised_return"] = (show["annualised_return"] * 100).round(2)
    show["annualised_volatility"] = (show["annualised_volatility"] * 100).round(2)
    show["max_drawdown"] = (show["max_drawdown"] * 100).round(2)
    if "turnover" in show.columns:
        show["turnover"] = show["turnover"].round(2)
    return show.rename(columns={
        "sharpe_ratio": "Sharpe", "annualised_return": "ann ret %",
        "annualised_volatility": "ann vol %", "max_drawdown": "max DD %"})


def print_summary(metrics: pd.DataFrame, fusion_table: pd.DataFrame,
                  vt_table: pd.DataFrame) -> None:
    print("\n" + "=" * 76)
    print("STATION 3 SUMMARY - out-of-sample walk-forward backtest (rf = 0)")
    print("=" * 76)
    cols = ["fund", "sharpe_ratio", "annualised_return",
            "annualised_volatility", "max_drawdown", "turnover"]
    show = _fmt_metric_table(metrics, cols)
    print(show.to_string(index=False))

    print("\nPROMPT_02 NEW GROUPING FUNDS (equal-weight + risk parity only)")
    grp = metrics[metrics["fund"].map(
        lambda f: pf.parse_fund_id(f)[0] in
        (list(pf.SECTOR_CLUSTERS) + list(pf.CRYPTO_THEMES)))]
    gshow = _fmt_metric_table(grp, cols)
    print(gshow.to_string(index=False))

    print("\nFUSION BASELINE (equity min-variance base; before transaction costs)")
    ft = fusion_table[["fund", "lambda", "sharpe_ratio", "annualised_return",
                       "annualised_volatility", "max_drawdown", "turnover"]].copy()
    ft["sharpe_ratio"] = ft["sharpe_ratio"].round(3)
    ft["annualised_return"] = (ft["annualised_return"] * 100).round(2)
    ft["annualised_volatility"] = (ft["annualised_volatility"] * 100).round(2)
    ft["max_drawdown"] = (ft["max_drawdown"] * 100).round(2)
    ft["turnover"] = ft["turnover"].round(2)
    ft = ft.rename(columns={
        "sharpe_ratio": "Sharpe", "annualised_return": "ann ret %",
        "annualised_volatility": "ann vol %", "max_drawdown": "max DD %"})
    print(ft.to_string(index=False))

    print("\nVOL-TARGETING OVERLAY "
          "(initial estimation-window target vol; k_t clipped to [0.5, 1.5])")
    vt_cols = ["fund", "annualised_return", "annualised_volatility",
               "sharpe_ratio", "max_drawdown"]
    vshow = _fmt_metric_table(vt_table, vt_cols)
    print(vshow.to_string(index=False))
    print("=" * 76)


def main():
    _t("Part B Station 3 pipeline start")
    eq, cr, eq_wide, cr_wide, combined_wide = load_panels()
    panels = {"equity": eq_wide, "crypto": cr_wide, "combined": combined_wide}
    fund_results = backtest_funds(eq, cr, eq_wide, cr_wide, combined_wide)
    vt_parts, vt_table = build_vol_target(fund_results, panels)
    merged, aligned, _lagged, index_long = build_sentiment(eq)
    fusion_parts = build_fusion(fund_results, eq_wide, aligned)
    metrics = save_funds_and_metrics(fund_results, fusion_parts, vt_parts)
    save_display_names()
    save_fund_fees()
    make_figures(fund_results, metrics, merged, index_long, fusion_parts, eq, vt_parts)
    print_summary(metrics, fusion_parts[4], vt_table)
    _t("done")


if __name__ == "__main__":
    main()
