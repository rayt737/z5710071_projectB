"""Station 3 - figures for the Part B report (self-contained exhibits).

Every figure is produced through src/style.py so all Part B figures share the
same design system as Part A (visual consistency across both reports), and every
figure states its sample period, labels its axes, and notes its data source.
"""
from __future__ import annotations

import pathlib

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import branding as brand
from src import style as sty
from src.portfolios import FAMILY_LABELS, METHOD_LABELS, parse_fund_id

FIGDIR = pathlib.Path("results") / "figures"


def _period(dates: pd.Series | pd.Index) -> str:
    """Month-Year range of a date collection (values must be datetimes).

    Always derived from the dates themselves (a DatetimeIndex or an explicit
    date column) - never from a positional/RangeIndex and never from a returns
    value, which would be read as nanoseconds since epoch ("Jan 1970").
    """
    dmin = pd.Timestamp(pd.Series(dates).min())
    dmax = pd.Timestamp(pd.Series(dates).max())
    return f"{dmin.strftime('%b %Y')} - {dmax.strftime('%b %Y')}"


def _caption(source: str, period: str, content: str) -> str:
    """Self-contained figure caption: source, sample period, and a line that
    describes what THIS figure actually shows (not a copy-pasted default)."""
    return f"Source: {source}. Sample period {period}. {content}"


# ---------------------------------------------------------------------------
# Performance metrics table
# ---------------------------------------------------------------------------

def fig_metrics_table(metrics: pd.DataFrame, filename: str = "performance_metrics_table.png"):
    """Render the performance-metrics table (all 22 funds) cleanly for the report."""
    fig, ax = sty.new_fig(figsize=(12, 8))
    ax.axis("off")

    disp = pd.DataFrame({
        "Fund": metrics["fund"].map(
            lambda f: brand.wrap_display_name(brand.fund_display_name(f), 30)),
        "Ann. return %": (metrics["annualised_return"] * 100).round(1),
        "Ann. vol %": (metrics["annualised_volatility"] * 100).round(1),
        "Sharpe": metrics["sharpe_ratio"].round(2),
        "Max DD %": (metrics["max_drawdown"] * 100).round(1),
        "Total ret %": (metrics["total_return"] * 100).round(1),
        "Turnover": metrics["turnover"].round(2),
    })

    tbl = ax.table(
        cellText=disp.values,
        colLabels=list(disp.columns),
        cellLoc="center",
        loc="center",
        colWidths=[0.26, 0.11, 0.10, 0.08, 0.10, 0.12, 0.08],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(7.5)
    tbl.scale(1.0, 1.25)
    for (r, c), cell in tbl.get_celld().items():
        if r == 0:
            cell.set_facecolor(sty.NAVY)
            cell.set_text_props(color="white", weight="bold")
        elif r % 2 == 0:
            cell.set_facecolor("#eef0f4")

    ax.set_title(
        "Performance metrics across 22 funds — out-of-sample backtest\n"
        "rf = 0, annualisation sqrt(252) equity/combined, sqrt(365) crypto",
        fontsize=11, color=sty.NAVY,
    )
    period = f"{metrics['first_live_date'].min()} to {metrics['last_date'].max()}"
    caption = (f"Source: results/tables/performance_metrics.csv. "
               f"Sample period {period}.")
    sty.save_fig(fig, filename, caption=caption)


# ---------------------------------------------------------------------------
# Growth of $1
# ---------------------------------------------------------------------------

def fig_growth_of_1(
    fund_returns_long: pd.DataFrame,
    family: str,
    filename: str,
):
    """Growth of $1 for one universe, all methods overlaid (end-labelled)."""
    wide = fund_returns_long[fund_returns_long["fund"].str.startswith(family)]
    fig, ax = sty.new_fig(figsize=(10, 5.5))
    series = []
    for i, method in enumerate(METHOD_LABELS):
        sub = wide[wide["fund"] == f"{family}_{method}"]
        if sub.empty:
            continue
        ts = sub.set_index("date")["return"].sort_index()
        growth = (1.0 + ts).cumprod()
        color = sty.PALETTE[i % len(sty.PALETTE)]
        label = brand.fund_display_name(f"{family}_{method}")
        ax.plot(growth.index, growth.values, label=label,
                color=color, linewidth=1.8)
        series.append((label, growth, color))
    ax.axhline(1.0, color=sty.GREY, linewidth=1, linestyle="--")
    ax.set_xlabel("Date")
    ax.set_ylabel("Growth of $1 invested")
    ax.set_title(f"{brand.family_display_prefix(family)} funds — growth of $1, all methods",
                 fontsize=13, color=sty.NAVY)
    ax.legend(title="Method", loc="best", fontsize=sty.FONT_LEGEND)
    if series:
        x_end = series[0][1].index[-1]
        sty.label_end_values(ax, [(lbl, float(growth.iloc[-1]), color)
                                  for lbl, growth, color in series], x_end)
    sty.format_date_axis(ax, max_ticks=6)
    period = _period(pd.Series(fund_returns_long["date"].unique()).sort_values())
    sty.save_fig(fig, filename, caption=_caption(
        f"results/data/fund_returns.csv ({FAMILY_LABELS[family].lower()} family)", period,
        "Growth is simple daily returns compounded from $1."))


# ---------------------------------------------------------------------------
# Drawdown
# ---------------------------------------------------------------------------

def fig_drawdown(returns: pd.Series, fund_label: str, filename: str, fund_id: str = ""):
    """Drawdown of one fund, shaded fill.

    ``fund_label`` is the investor-facing display name (title); ``fund_id`` is
    the technical id, used in the caption for CSV traceability.
    """
    cum = (1.0 + returns).cumprod()
    dd = cum / cum.cummax() - 1.0
    fig, ax = sty.new_fig(figsize=(10, 4.8))
    ax.fill_between(dd.index, dd.values * 100, 0, color=sty.CORAL, alpha=0.45, linewidth=0)
    ax.plot(dd.index, dd.values * 100, color=sty.CORAL, linewidth=1.2)
    ax.set_xlabel("Date")
    ax.set_ylabel("Drawdown (%)")
    ax.set_title(f"{fund_label} — drawdown from peak", fontsize=13, color=sty.NAVY)
    ax.yaxis.set_major_formatter(sty.pct_formatter())
    sty.format_date_axis(ax, max_ticks=6)
    sty.save_fig(fig, filename, caption=_caption(
        f"results/data/fund_returns.csv ({fund_id or fund_label})", _period(returns.index),
        "Drawdown is the cumulative fall from the running peak; returns are simple daily returns."))


# ---------------------------------------------------------------------------
# Portfolio weights over time (stacked area by sector)
# ---------------------------------------------------------------------------

def fig_weights_stacked(
    weights: pd.DataFrame,
    sector_map: dict[str, str],
    fund_label: str,
    filename: str,
    fund_id: str = "",
    crypto_suffix: tuple = ("-USD",),
):
    """Stacked area of target weights by sector over rebalances.

    Equity tickers are grouped into their sectors; any ticker not in sector_map
    (e.g. crypto) is shown as one 'Crypto' band.
    """
    def group(t):
        if t in sector_map:
            return sector_map[t]
        if t.endswith(crypto_suffix):
            return "Crypto"
        return "Other"

    grouped = weights.copy()
    grouped.columns = [group(c) for c in weights.columns]
    stacked = grouped.T.groupby(level=0).sum().T
    stacked = stacked.reindex(sorted(stacked.columns, key=lambda c: -stacked[c].iloc[-1]),
                              axis=1)

    fig, ax = sty.new_fig(figsize=(10, 5.5))
    x = np.arange(len(stacked))
    bottom = np.zeros(len(stacked))
    colors = plt.cm.viridis(np.linspace(0.15, 0.9, stacked.shape[1]))
    for i, col in enumerate(stacked.columns):
        ax.bar(x, stacked[col].values, bottom=bottom, label=col,
               color=colors[i], width=1.0)
        bottom += stacked[col].values

    tick_every = max(1, len(stacked) // 6)
    ax.set_xticks(x[::tick_every])
    labels = [stacked.index[i].strftime("%b %Y") for i in range(0, len(stacked), tick_every)]
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
    ax.set_xlabel("Rebalance date")
    ax.set_ylabel("Target weight")
    ax.set_title(f"{fund_label} - target weights by sector at each monthly rebalance",
                 fontsize=13, color=sty.NAVY)
    ax.legend(title="Sector", loc="best", fontsize=8, ncol=2, frameon=True)
    ax.set_ylim(0, 1.0)
    period = f"{stacked.index[0].strftime('%b %Y')} - {stacked.index[-1].strftime('%b %Y')}"
    sty.save_fig(fig, filename, caption=_caption(
        f"results/data/fund_weights.csv ({fund_id or fund_label})", period,
        "Weights are target allocations at each monthly rebalance."))


# ---------------------------------------------------------------------------
# Sharpe barplot
# ---------------------------------------------------------------------------

def fig_sharpe_barplot(metrics: pd.DataFrame, filename: str = "sharpe_barplot.png"):
    """Sharpe ratio barplot across all 22 funds (horizontal, sorted descending).

    Mirrors the Station 4 app's Compare-tab chart (prompt_06 item 3): long
    display names run down the y-axis so they never rotate or collide, funds
    are ordered by Sharpe descending, and the canvas height is sized by the
    number of funds so the wrapped labels keep clear vertical spacing
    (prompt_09 item 3).
    """
    df = metrics.copy()
    df = df.sort_values("sharpe_ratio", ascending=False).reset_index(drop=True)
    df["label"] = df["fund"].map(
        lambda f: brand.wrap_display_name(brand.fund_display_name(f), 26))
    family_color = {
        "equity": sty.NAVY, "crypto": sty.CORAL, "combined": sty.AMBER,
        "defensive": "#2a9d8f", "cyclical": "#264653",
        "growth_sensitive": "#8ab17d", "payments": "#e9c46a", "web3infra": "#a98467",
    }
    colors = [family_color[parse_fund_id(f)[0]] for f in df["fund"]]

    n = len(df)
    fig, ax = sty.new_fig(figsize=(11, 0.42 * n + 1.6))
    y = np.arange(n)
    bars = ax.barh(y, df["sharpe_ratio"].values, color=colors, height=0.7)
    ax.axvline(0, color=sty.GREY, linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels(df["label"].values, fontsize=8.5)
    ax.invert_yaxis()
    ax.margins(y=0.02)
    ax.set_ylabel("")
    ax.set_xlabel("Sharpe ratio (rf = 0)")
    ax.set_title("Out-of-sample Sharpe ratios across all 22 funds",
                 fontsize=13, color=sty.NAVY)
    for bar, v in zip(bars, df["sharpe_ratio"].values):
        ax.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height() / 2,
                f"{v:.2f}", ha="left", va="center", fontsize=7.5, color=sty.GREY)
    from matplotlib.patches import Patch
    handles = [Patch(color=c, label=FAMILY_LABELS[family]) for family, c in family_color.items()]
    ax.legend(handles=handles, title="Asset family", loc="lower right", fontsize=9)
    period = f"{df['first_live_date'].min()} to {df['last_date'].max()}"
    sty.save_fig(fig, filename, caption=_caption(
        "results/tables/performance_metrics.csv", period,
        "Sharpe ratios use rf = 0 with annualisation sqrt(252) for equity/combined "
        "and sqrt(365) for crypto."))


# ---------------------------------------------------------------------------
# Sentiment: plain VADER vs finVADER-lite
# ---------------------------------------------------------------------------

def fig_sentiment_comparison(
    plain: pd.Series,
    extended: pd.Series,
    filename: str = "sentiment_lexicon_comparison.png",
):
    """Before/after lexicon comparison: score distribution + monthly mean series."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.6))
    for ax in (ax1, ax2):
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_facecolor(sty.BG)
        ax.grid(True, linestyle="--", linewidth=0.4, color=sty.LIGHT_GREY, axis="both")

    bins = np.linspace(-1, 1, 61)
    ax1.hist(plain.dropna(), bins=bins, alpha=0.6, color=sty.GREY,
             label="Plain VADER", density=True)
    ax1.hist(extended.dropna(), bins=bins, alpha=0.5, color=sty.CORAL,
             label="finVADER-lite", density=True)
    ax1.set_xlabel("Compound score")
    ax1.set_ylabel("Density")
    ax1.set_title("Per-headline score distribution", fontsize=12, color=sty.NAVY)
    ax1.legend(fontsize=9)
    ax1.text(0.02, 0.97, f"neutral (|c|<0.05): {float((extended.abs() < 0.05).mean()):.0%} ext",
             transform=ax1.transAxes, fontsize=8, va="top", color=sty.GREY)

    p = plain.copy()
    e = extended.copy()
    p.index = plain.index
    e.index = extended.index
    monthly_p = p.groupby(p.index.to_period("M")).mean()
    monthly_e = e.groupby(e.index.to_period("M")).mean()
    ax2.plot(monthly_p.index.to_timestamp(), monthly_p.values, label="Plain VADER",
             color=sty.GREY, linewidth=1.6)
    ax2.plot(monthly_e.index.to_timestamp(), monthly_e.values, label="finVADER-lite",
             color=sty.CORAL, linewidth=1.8)
    ax2.set_xlabel("Date")
    ax2.set_ylabel("Mean compound score")
    ax2.set_title("Monthly mean headline sentiment", fontsize=12, color=sty.NAVY)
    ax2.legend(fontsize=9)
    sty.format_date_axis(ax2, max_ticks=6)
    fig.suptitle("Plain VADER vs finVADER-lite (35-term LM-grounded lexicon)",
                 fontsize=13, color=sty.NAVY)
    fig.tight_layout(rect=[0, 0.05, 1, 1])
    period = f"{plain.index.min().strftime('%b %Y')} - {plain.index.max().strftime('%b %Y')}"
    sty.save_fig(fig, filename, caption=_caption(
        "results/data/headline_sentiment.csv (all headlines, 2020-2023)", period,
        "Scores are per-headline VADER compound sentiment (plain vs finVADER-lite)."))


# ---------------------------------------------------------------------------
# Sector sentiment index over time
# ---------------------------------------------------------------------------

def fig_sector_sentiment(index_long: pd.DataFrame, filename: str = "sector_sentiment_index.png"):
    """Daily sector sentiment index over time for all 10 sectors."""
    fig, ax = sty.new_fig(figsize=(10.5, 5.5))
    pivot = index_long.pivot(index="date", columns="sector", values="sentiment")
    pivot = pivot.reindex(sorted(pivot.columns), axis=1)
    for i, col in enumerate(pivot.columns):
        ax.plot(pivot.index, pivot[col].values, label=col,
                color=sty.PALETTE[i % len(sty.PALETTE)], linewidth=1.2)
    ax.axhline(0, color=sty.GREY, linewidth=1, linestyle="--")
    ax.set_xlabel("Date")
    ax.set_ylabel("Sentiment score (finVADER-lite, lagged 1 trading day)")
    ax.set_title("Sector sentiment index over time (equal-weight stocks, "
                 "no-news days carried forward)", fontsize=12.5, color=sty.NAVY)
    ax.legend(title="Sector", ncol=2, fontsize=8, loc="best")
    ax.margins(x=0)
    sty.format_date_axis(ax, max_ticks=6)
    period = f"{pivot.index.min().strftime('%b %Y')} - {pivot.index.max().strftime('%b %Y')}"
    sty.save_fig(fig, filename, caption=_caption(
        "results/data/sector_sentiment_index.csv (lagged 1 trading day)", period,
        "Index is the lagged sector-level sentiment signal."))


# ---------------------------------------------------------------------------
# Fusion comparison
# ---------------------------------------------------------------------------

def fig_fusion_growth(
    base: pd.Series,
    momentum: pd.Series,
    contrarian: pd.Series,
    filename: str = "fusion_growth_comparison.png",
):
    """Growth of $1: equity min-variance base vs momentum and contrarian tilts."""
    base_name = brand.fund_display_name(brand.FUSION_BASE_FUND)
    fig, ax = sty.new_fig(figsize=(10, 5.2))
    plotted = []
    for label, ts, color in [
        (base_name, base, sty.NAVY),
        (brand.FUSION_DISPLAY_NAMES["momentum"], momentum, sty.CORAL),
        (brand.FUSION_DISPLAY_NAMES["contrarian"], contrarian, sty.AMBER),
    ]:
        g = (1.0 + ts).cumprod()
        ax.plot(g.index, g.values, label=label, color=color, linewidth=1.8)
        plotted.append((label, g, color))
    ax.axhline(1.0, color=sty.GREY, linewidth=1, linestyle="--")
    ax.set_xlabel("Date")
    ax.set_ylabel("Growth of $1 invested")
    ax.set_title(f"Sentiment fusion on the {base_name} (before transaction costs)",
                 fontsize=12.5, color=sty.NAVY)
    ax.legend(loc="best", fontsize=8.5)
    x_end = base.index[-1]
    sty.label_end_values(ax, [(lbl, float(g.iloc[-1]), color)
                              for lbl, g, color in plotted], x_end)
    sty.format_date_axis(ax, max_ticks=6)
    period = f"{base.index.min().strftime('%b %Y')} - {base.index.max().strftime('%b %Y')}"
    sty.save_fig(fig, filename, caption=_caption(
        "results/tables/fusion_comparison.csv", period,
        "Growth is simple daily returns compounded from $1; fusion adds a sentiment "
        "tilt before transaction costs."))


# ---------------------------------------------------------------------------
# New fund groupings (prompt_02): growth of $1 across several families
# ---------------------------------------------------------------------------

def fig_growth_groupings(
    fund_returns_long: pd.DataFrame,
    families: list[str],
    filename: str,
    title: str,
):
    """Growth of $1 for all funds in several grouping families (end-labelled).

    One line per fund (e.g. 'Defensive Equal-Weight'), colour-cycled through the
    shared palette, with the Part A end-of-line value labels.
    """
    fig, ax = sty.new_fig(figsize=(10.5, 5.8))
    plotted = []
    funds = sorted(f for f in fund_returns_long["fund"].unique()
                   if any(f.startswith(fam + "_") for fam in families))
    for i, fund in enumerate(funds):
        sub = fund_returns_long[fund_returns_long["fund"] == fund]
        ts = sub.set_index("date")["return"].sort_index()
        growth = (1.0 + ts).cumprod()
        color = sty.PALETTE[i % len(sty.PALETTE)]
        label = brand.fund_display_name(fund)
        ax.plot(growth.index, growth.values, label=label, color=color, linewidth=1.8)
        plotted.append((label, growth, color))
    ax.axhline(1.0, color=sty.GREY, linewidth=1, linestyle="--")
    ax.set_xlabel("Date")
    ax.set_ylabel("Growth of $1 invested")
    ax.set_title(title, fontsize=12.5, color=sty.NAVY)
    ax.legend(loc="best", fontsize=sty.FONT_LEGEND, ncol=2)
    if plotted:
        x_end = plotted[0][1].index[-1]
        sty.label_end_values(ax, [(lbl, float(g.iloc[-1]), color)
                                  for lbl, g, color in plotted], x_end)
    sty.format_date_axis(ax, max_ticks=6)
    period = _period(pd.Series(fund_returns_long["date"].unique()).sort_values())
    fams = ", ".join(sorted({
        parse_fund_id(f)[0]
        for f in fund_returns_long["fund"].unique()
        if any(f.startswith(fam + "_") for fam in families)}))
    sty.save_fig(fig, filename, caption=_caption(
        f"results/data/fund_returns.csv ({fams} families)", period,
        "Growth is simple daily returns compounded from $1; groupings use equal-weight "
        "and risk parity only."))


# ---------------------------------------------------------------------------
# Volatility-targeting overlay (prompt_02): growth + scaling factor
# ---------------------------------------------------------------------------

def fig_vol_target_growth(
    base: pd.Series,
    scaled: pd.Series,
    fund_label: str,
    filename: str,
    *,
    managed_label: str = "",
    fund_id: str = "",
):
    """Growth of $1: base fund vs its vol-targeted overlay (end-labelled).

    ``fund_label``/``managed_label`` are the investor-facing display names of
    the base fund and its managed-vol overlay; ``fund_id`` is the technical id
    used in the caption for CSV traceability.
    """
    fig, ax = sty.new_fig(figsize=(10, 5.2))
    plotted = []
    for label, ts, color in [
        (fund_label, base, sty.NAVY),
        (managed_label or f"{fund_label} vol-targeted", scaled, sty.CORAL),
    ]:
        g = (1.0 + ts).cumprod()
        ax.plot(g.index, g.values, label=label, color=color, linewidth=1.8)
        plotted.append((label, g, color))
    ax.axhline(1.0, color=sty.GREY, linewidth=1, linestyle="--")
    ax.set_xlabel("Date")
    ax.set_ylabel("Growth of $1 invested")
    ax.set_title(f"Volatility targeting on the {fund_label}",
                 fontsize=12.5, color=sty.NAVY)
    ax.legend(loc="best", fontsize=9)
    x_end = base.index[-1]
    sty.label_end_values(ax, [(lbl, float(g.iloc[-1]), color)
                              for lbl, g, color in plotted], x_end)
    sty.format_date_axis(ax, max_ticks=6)
    period = f"{base.index.min().strftime('%b %Y')} - {base.index.max().strftime('%b %Y')}"
    sty.save_fig(fig, filename, caption=_caption(
        f"results/tables/vol_target_comparison.csv ({fund_id or fund_label})", period,
        "Growth is simple daily returns compounded from $1; the overlay scales exposure "
        "toward the fund's initial-estimation-window volatility (fixed before live trading)."))


def fig_vol_target_scaling(
    k: pd.Series,
    fund_label: str,
    filename: str,
    clip: tuple = (0.5, 1.5),
):
    """The vol-targeting scaling factor k_t over time.

    k_t is real, causal data pinned at the clip band when trailing vol falls
    far below the target (k_t = 1.5 during calm stretches) - it is not NaN, so
    the fix is visual: a bold, solid, topmost k_t line plus a light band over
    the periods where the clip binds (prompt_09 item 5).
    """
    fig, ax = sty.new_fig(figsize=(10, 4.2))
    lower, upper = clip
    at_clip = k.values >= upper
    if at_clip.any():
        ax.fill_between(k.index, lower, upper, where=at_clip,
                        color=sty.CORAL, alpha=0.12, linewidth=0,
                        label="Pinned at clip band")
    ax.plot(k.index, k.values, color=sty.NAVY, linewidth=1.8,
            zorder=5, solid_capstyle="round")
    ax.axhline(1.0, color=sty.GREY, linewidth=1, linestyle="--", zorder=3)
    for bound in clip:
        ax.axhline(bound, color=sty.CORAL, linewidth=0.8, linestyle=":", zorder=3)
    ax.set_xlabel("Date")
    ax.set_ylabel("Scaling factor $k_t$")
    ax.set_title(f"{fund_label} — vol-targeting scaling factor (clip {clip})",
                 fontsize=12.5, color=sty.NAVY)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _pos: f"{v:.2f}"))
    if at_clip.any():
        ax.legend(loc="best", fontsize=8)
    sty.format_date_axis(ax, max_ticks=6)
    period = f"{k.index.min().strftime('%b %Y')} - {k.index.max().strftime('%b %Y')}"
    sty.save_fig(fig, filename, caption=_caption(
        "results/tables/vol_target_comparison.csv", period,
        f"$k_t$ = target vol / trailing 60-day realised vol, clipped to {clip}; "
        "uses only returns strictly before t."))
