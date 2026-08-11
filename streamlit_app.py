"""Invesper Systematic Funds - Station 4 app (design pass, prompt_06).

Reads precomputed ``results/`` only. No backtest, optimiser, or sentiment
scorer is imported or run here (see ai/prompts/prompt_04.md non-negotiables);
all figures are built live from the published CSVs so they stay consistent
with whatever is in ``results/``. Fund labels come from
``results/data/fund_display_names.csv`` - never a raw fund id. Fees come from
``results/data/fund_fees.csv``; the full per-headline scoring table is never
read at app runtime (the Sentiment tab shows the sector index and the
fear/greed gauge only - the precomputed lexicon-comparison summary stays in
``results/`` for the report, not the app). Point-in-time dates render via
``app.formatting.format_date`` (prompt_06 item 1). Branding: the Invesper
logo (shown beside the page title) and shield icon (browser tab) load from
``assets/``.

Run locally:   streamlit run streamlit_app.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from app import data as app_data
from app import formatting as fmt

st.set_page_config(page_title="Invesper", page_icon="assets/invesper_icon.png", layout="wide")

_PERCENT_CFG = st.column_config.NumberColumn(format="percent")


@st.cache_data(ttl=86_400, show_spinner="Loading published results...")
def _load_data() -> app_data.AppData:
    return app_data.build_app_data()


def _source_caption(fig_or_table: str, sources: str) -> None:
    st.caption(f"Source: {sources}. {fig_or_table}")


def render_compare(d: app_data.AppData) -> None:
    st.subheader("Compare funds")
    universe = st.radio("Universe", list(app_data.UNIVERSES), horizontal=True, key="cmp_universe")
    funds = d.universe_funds[universe]
    sub = d.metrics.set_index("fund").loc[funds].reset_index()

    table = sub.rename(columns={
        "display_name": "Fund",
        "type": "Type",
        **{c: fmt.metric_label(c) for c in app_data.METRIC_COLS},
    }).copy()
    table = table[["Fund", "Type", *[fmt.metric_label(c) for c in app_data.METRIC_COLS]]]
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        column_config={
            "Fund": st.column_config.TextColumn("Fund"),
            "Type": st.column_config.TextColumn("Type"),
            fmt.metric_label("annualised_return"): _PERCENT_CFG,
            fmt.metric_label("annualised_volatility"): _PERCENT_CFG,
            fmt.metric_label("sharpe_ratio"): st.column_config.NumberColumn(format="%.2f"),
            fmt.metric_label("max_drawdown"): _PERCENT_CFG,
        },
    )
    _source_caption(
        "Sharpe ratios use rf = 0; equity/combined annualised with sqrt(252), "
        "crypto with sqrt(365).",
        "results/tables/performance_metrics.csv, fusion_comparison.csv, vol_target_comparison.csv",
    )

    # Horizontal Sharpe chart: long display names go on the y-axis, so no
    # rotated/overlapping labels regardless of name length (prompt_06 item 3).
    # Height scales with the number of funds so wrapped multi-line labels keep
    # clear vertical spacing. (plotly only supports categorygap on the x-axis,
    # so the gap is left at default for horizontal bars.)
    chart_sub = sub.sort_values("sharpe_ratio").copy()
    chart_sub["label"] = chart_sub["display_name"].map(
        lambda n: app_data.wrap_label(n, 26))
    chart = px.bar(
        chart_sub,
        x="sharpe_ratio",
        y="label",
        orientation="h",
        color="type",
        labels={"x": "Sharpe ratio", "y": "", "color": ""},
        title=f"{universe} Sharpe Ratio",
    )
    chart.update_layout(
        height=240 + 45 * len(chart_sub),
        xaxis={"title": "Sharpe ratio", "automargin": True},
        yaxis={"automargin": True, "title": ""},
        legend={"orientation": "h", "y": -0.18},
        margin={"t": 60, "b": 40, "l": 60, "r": 60},
    )
    chart.update_traces(texttemplate="%{x:.2f}", textposition="outside")
    st.plotly_chart(chart, width="stretch")


def render_fact_sheet(d: app_data.AppData) -> None:
    st.subheader("Fund fact sheet")
    universe = st.radio("Universe", list(app_data.UNIVERSES), horizontal=True, key="fs_universe")
    funds = d.universe_funds[universe]
    options = {d.lookup[f]: f for f in funds}
    label = st.selectbox("Fund", list(options), key="fs_fund")
    fund = options[label]
    row = d.metrics.set_index("fund").loc[fund]

    st.markdown(f"### {row['display_name']}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Annualised return", f"{row['annualised_return']:.1%}")
    c2.metric("Annualised volatility", f"{row['annualised_volatility']:.1%}")
    c3.metric("Sharpe ratio", f"{row['sharpe_ratio']:.2f}")
    c4.metric("Max drawdown", f"{row['max_drawdown']:.1%}")
    _source_caption(
        f"Out-of-sample {fmt.format_date('2021-01-01')} to "
        f"{fmt.format_date('2023-12-31')}. rf = 0; sqrt(252) "
        "equity/combined, sqrt(365) crypto.",
        row["source"],
    )

    series = app_data.fund_return_series(d.returns, fund)
    if series.empty:
        st.info(
            "No return history for this fund yet - rerun "
            "scripts/run_part_b.py to republish the results."
        )
        return

    growth = app_data.growth_of_1(series)
    dd = app_data.drawdown_from_returns(series)
    g1, g2 = st.columns(2)
    with g1:
        fig = px.line(x=growth.index, y=growth.values,
                      labels={"x": "", "y": "Growth of $1"},
                      title="Growth of $1")
        fig.update_traces(line={"color": "#003366"})
        fig.update_layout(height=360, margin={"t": 50, "b": 20, "l": 50, "r": 20})
        st.plotly_chart(fig, width="stretch")
    with g2:
        fig = px.area(x=dd.index, y=dd.values,
                      labels={"x": "", "y": "Drawdown"},
                      title="Drawdown")
        fig.update_traces(line={"color": "#a50000"}, fillcolor="rgba(165,0,0,0.25)")
        fig.update_layout(height=360, margin={"t": 50, "b": 20, "l": 50, "r": 20})
        st.plotly_chart(fig, width="stretch")

    # Vol-targeted variants don't reallocate across assets - the overlay is a
    # portfolio-level scalar - so their holdings are the base fund's, shown
    # here with an explanatory caption (prompt_05 part 2).
    is_vol_target = fund.endswith(app_data.VOL_TARGET_SUFFIX)
    hold_fund = app_data.base_fund_of(fund)
    holds, latest_date = app_data.latest_holdings(d.weights, hold_fund)
    if latest_date is not None:
        st.markdown(f"### Current holdings (as of {fmt.format_date(latest_date)})")
    top = holds.head(15)
    if len(holds) > len(top):
        other = {"ticker": "Other", "weight": float(holds["weight"].iloc[len(top):].sum())}
        top = pd.concat([top, pd.DataFrame([other])], ignore_index=True)
    fig = px.bar(top, x="weight", y="ticker", orientation="h",
                 labels={"weight": "Target weight", "ticker": ""},
                 title=f"{len(holds)} holdings - target weights")
    fig.update_layout(height=420, margin={"t": 50, "b": 20, "l": 40, "r": 40})
    fig.update_traces(marker={"color": "#003366"})
    st.plotly_chart(fig, width="stretch")
    if is_vol_target:
        base_name = d.lookup[hold_fund]
        st.caption(
            "Volatility targeting scales overall exposure, not individual "
            f"holdings - shown here are the underlying {base_name}'s holdings."
        )
    _source_caption(
        "Weights are target allocations at the fund's most recent monthly rebalance.",
        "results/data/fund_weights.csv",
    )


def render_sentiment(d: app_data.AppData) -> None:
    st.subheader("Sector sentiment")
    selected = st.multiselect(
        "Sectors", d.sectors, default=d.sectors, key="sent_sectors"
    )
    sub = d.sector.loc[d.sector["sector"].isin(selected)]
    if sub.empty:
        st.info("Select at least one sector.")
        return
    fig = px.line(
        sub, x="date", y="sentiment_aligned", color="sector",
        labels={"date": "", "sentiment_aligned": "Sentiment index",
                "sector": "Sector"},
        title="Sector sentiment index over time",
    )
    fig.update_layout(height=440, margin={"t": 50, "b": 20, "l": 50, "r": 20})
    st.plotly_chart(fig, width="stretch")
    _source_caption(
        "The index shown is the sector-level display version; the investable "
        "signal (the 'sentiment' column) is lagged one trading day.",
        "results/data/sector_sentiment_index.csv",
    )

    st.subheader("Market-wide sentiment (fear / greed gauge)")
    mkt = d.market_sentiment
    scaled = app_data.rescale_0_100(mkt)
    latest_date = scaled.index[-1]
    latest_raw = float(mkt.iloc[-1])
    latest_value = float(scaled.iloc[-1])
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=latest_value,
        number={"suffix": " / 100"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "#003366"},
            "steps": [
                {"range": [0, 40], "color": "#ffcccc"},
                {"range": [40, 60], "color": "#ffe6b3"},
                {"range": [60, 100], "color": "#ccffcc"},
            ],
            "threshold": {
                "line": {"color": "#003366", "width": 4},
                "value": latest_value,
            },
        },
        title={"text": "0 = Fear - 100 = Greed"},
    ))
    fig.update_layout(height=380, margin={"t": 70, "b": 20, "l": 40, "r": 40})
    st.plotly_chart(fig, width="stretch")
    latest_str = fmt.format_date(latest_date)
    st.markdown(
        f"Latest reading on **{latest_str}**: market-wide sector sentiment "
        f"{latest_raw:+.3f} (raw index) -> **{latest_value:.0f} / 100** "
        "(greed-leaning)" if latest_value >= 50 else
        f"Latest reading on **{latest_str}**: market-wide sector sentiment "
        f"{latest_raw:+.3f} (raw index) -> **{latest_value:.0f} / 100** "
        "(fear-leaning)"
    )
    st.caption(
        "Current reading (unlagged) - for display only; fund construction uses "
        "the lagged signal shown in the sector chart."
    )
    _source_caption(
        "Equal-weighted average of the 10 sector indices on the latest date. The "
        f"0-100 scale rescales that average across the full published sample "
        f"({fmt.format_date(mkt.index.min())} to {fmt.format_date(mkt.index.max())}) "
        "- if the sample changes, the scale moves.",
        "results/data/sector_sentiment_index.csv",
    )


def render_allocation(d: app_data.AppData) -> None:
    st.subheader("Build an allocation")
    _source_caption(
        f"Blends the published daily return series of all {len(d.allocation_funds)} "
        "funds - the 22 base funds plus the fusion and vol-targeted variants - "
        "across all three universes; weights are normalised to 100%. Each fund "
        "is priced at its own fixed annual management fee "
        "(results/data/fund_fees.csv); the blended fee below is the weighted "
        "average across your selection.",
        "results/data/fund_returns.csv",
    )
    options = {d.lookup[f]: f for f in d.allocation_funds}
    selected_labels = st.multiselect(
        "Funds", list(options), default=None, key="alloc_funds",
        placeholder="Pick any combination of funds across the three universes...",
    )
    selected = [options[label] for label in selected_labels]
    if not selected:
        st.info("Select at least one fund to build an allocation.")
        return

    default_w = round(100.0 / len(selected), 1)
    st.markdown("**Target weights (raw, normalised below)**")
    cols = st.columns(min(len(selected), 3))
    raw = {}
    for i, fund in enumerate(selected):
        with cols[i % len(cols)]:
            raw[fund] = st.slider(
                d.lookup[fund], 0.0, 100.0, value=default_w, step=1.0,
                key=f"alloc_w_{fund}",
            )
            st.caption(f"Fee: {d.fees[fund]:.2%} p.a.")
    total = sum(raw.values())
    st.caption(
        f"Raw weights sum to **{total:.0f}%**; the blended allocation below is "
        "normalised to 100%."
    )
    if total <= 0:
        st.info("Give at least one fund a positive weight.")
        return
    norm = {f: w / total for f, w in raw.items()}
    blended = app_data.blended_fee(norm, d.fees)

    alloc = pd.DataFrame({
        "Fund": [d.lookup[f] for f in selected],
        "Normalised weight": [f"{norm[f]:.1%}" for f in selected],
        "Fee": [f"{d.fees[f]:.2%} p.a." for f in selected],
    })
    st.dataframe(alloc, hide_index=True, width="stretch")
    st.markdown(f"**Blended management fee: {blended:.2%} p.a.**")
    st.caption(
        "Invesper charges no per-trade commission, consistent with the "
        "zero-commission model most modern brokerages and robo-advisors have "
        "adopted since 2019; it earns instead through each fund's fixed annual "
        "management fee on assets under management."
    )

    growth = app_data.blend_portfolio(d.returns, selected, norm, blended)
    fig = px.line(
        growth,
        labels={"date": "", "value": "Growth of $1", "variable": ""},
        title=f"Blended growth of $1 (gross vs net of {blended:.2%} p.a. fee)",
    )
    fig.for_each_trace(lambda t: t.update(name={
        "gross": "Gross of fee", "net": f"Net of fee ({blended:.2%} p.a.)",
    }[t.name]))
    fig.update_layout(height=440, margin={"t": 50, "b": 20, "l": 50, "r": 20})
    st.plotly_chart(fig, width="stretch")

    end = growth.iloc[-1]
    _source_caption(
        f"Growth of $1 from {fmt.format_date(growth.index[0])} to "
        f"{fmt.format_date(growth.index[-1])}. "
        f"Gross: ${end['gross']:.2f}; net of fee: ${end['net']:.2f}. The fee is "
        "charged daily on AUM at the blended fee / 365; a day a fund has no row "
        "for counts as 0% return.",
        "results/data/fund_returns.csv, results/data/fund_fees.csv",
    )

    _render_submit_portfolio(d, selected, norm, blended, growth)


def _unique_portfolio_name(base: str, existing: list[str]) -> str:
    """Make a portfolio name unique against the saved set ('X (2)', 'X (3)')."""
    if base not in existing:
        return base
    i = 2
    while f"{base} ({i})" in existing:
        i += 1
    return f"{base} ({i})"


def _render_submit_portfolio(
    d: app_data.AppData,
    selected: list[str],
    norm: dict[str, float],
    blended: float,
    growth: pd.DataFrame,
) -> None:
    """Submit-as-portfolio (prompt_06 item 7): saves a COPY of the current
    allocation - fund ids, weights, blended fee, and the already-computed
    gross/net growth series - into session_state. The working selection stays
    untouched so the user can keep adjusting and submit again. The name field's
    widget key rotates after each submit so it resets to the next sensible
    default ("Portfolio 2", "Portfolio 3", ...) instead of silently reusing
    the previous typed name."""
    st.markdown("### Save this allocation")
    saved = st.session_state.setdefault("saved_portfolios", [])
    default_name = f"Portfolio {len(saved) + 1}"
    n_submitted = st.session_state.setdefault("alloc_pf_submitted", 0)
    pf_name = st.text_input(
        "Portfolio name (optional - auto-uniquified)",
        value=default_name, key=f"alloc_pf_name_{n_submitted}",
    )
    if st.button("Submit portfolio", key="alloc_submit"):
        name = _unique_portfolio_name(
            pf_name.strip() or default_name, [p["name"] for p in saved])
        saved.append({
            "name": name,
            "funds": list(selected),
            "weights": dict(norm),
            "blended_fee": blended,
            "growth": growth,
        })
        st.session_state["alloc_pf_submitted"] = n_submitted + 1
        st.success(f"Saved {name!r} - see the Portfolio tab.")


def render_portfolio(d: app_data.AppData) -> None:
    st.subheader("Portfolio")
    saved = st.session_state.setdefault("saved_portfolios", [])
    st.caption(
        "Saved portfolios persist for this browser session only and will reset "
        "if the app restarts or the page is reloaded."
    )
    if not saved:
        st.info("No portfolios saved yet - build an allocation on the previous "
                "tab and submit it.")
        return

    for entry in saved:
        name = entry["name"]
        st.markdown(f"### {name}")
        comp = pd.DataFrame({
            "Fund": [d.lookup[f] for f in entry["funds"]],
            "Weight": [entry["weights"][f] for f in entry["funds"]],
        })
        st.markdown(
            ", ".join(f"{d.lookup[f]} ({entry['weights'][f]:.0%})"
                      for f in entry["funds"])
        )

        c1, c2 = st.columns([1, 2])
        with c1:
            pie = px.pie(comp, names="Fund", values="Weight", hole=0.4,
                         title="Composition")
            pie.update_layout(height=320, margin={"t": 50, "b": 20, "l": 20, "r": 20})
            st.plotly_chart(pie, width="stretch", key=f"pf_pie_{name}")
        with c2:
            metrics = app_data.portfolio_metrics(entry["growth"])
            gfig = px.line(
                entry["growth"],
                labels={"date": "", "value": "Growth of $1", "variable": ""},
                title=f"Growth of $1 (gross vs net of {entry['blended_fee']:.2%} p.a. fee)",
            )
            gfig.for_each_trace(lambda t: t.update(name={
                "gross": "Gross of fee",
                "net": f"Net of fee ({entry['blended_fee']:.2%} p.a.)",
            }[t.name]))
            gfig.update_layout(height=320, margin={"t": 50, "b": 20, "l": 50, "r": 20})
            st.plotly_chart(gfig, width="stretch", key=f"pf_growth_{name}")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Annualised return", f"{metrics['annualised_return']:.1%}")
        m2.metric("Annualised volatility", f"{metrics['annualised_volatility']:.1%}")
        m3.metric("Sharpe ratio", f"{metrics['sharpe_ratio']:.2f}")
        m4.metric("Max drawdown", f"{metrics['max_drawdown']:.1%}")
        st.caption(
            f"Blended management fee: {entry['blended_fee']:.2%} p.a. "
            "Annualised using this portfolio's actual observed trading calendar "
            f"(~{metrics['annualisation_factor']:.0f} days/year) - a blend that "
            "includes crypto funds genuinely trades closer to 365 days/year "
            "than equity's 252, so the factor is derived from the data, not "
            "assumed."
        )
        if st.button(f"Delete {name}", key=f"pf_del_{name}"):
            st.session_state["saved_portfolios"] = [
                p for p in st.session_state["saved_portfolios"] if p["name"] != name
            ]
            st.rerun()


def main() -> None:
    logo_col, title_col = st.columns([1, 6], vertical_alignment="center")
    with logo_col:
        st.image("assets/invesper_logo_full.png", width=110)
    with title_col:
        st.title("Invesper Systematic Funds")
    st.caption(
        "Out-of-sample fund performance, sector sentiment and portfolio tools, "
        "built live from the published results under results/. Out-of-sample "
        f"period {fmt.format_date('2021-01-01')} to {fmt.format_date('2023-12-31')}; "
        f"the sector sentiment index starts {fmt.format_date('2020-01-02')}."
    )
    try:
        d = _load_data()
    except FileNotFoundError as exc:
        st.error(str(exc))
        return
    if d.unclassified:
        st.warning(
            "Fund id(s) not classified into a universe (data may have drifted): "
            + ", ".join(d.unclassified)
        )

    tab_compare, tab_fact, tab_sent, tab_alloc, tab_portfolio = st.tabs(
        ["Compare funds", "Fund fact sheet", "Sentiment analytics",
         "Build an allocation", "Portfolio"]
    )
    with tab_compare:
        render_compare(d)
    with tab_fact:
        render_fact_sheet(d)
    with tab_sent:
        render_sentiment(d)
    with tab_alloc:
        render_allocation(d)
    with tab_portfolio:
        render_portfolio(d)


main()
