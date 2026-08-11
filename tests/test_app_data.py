"""Station 4 data-layer tests: universe derivation, display-name coverage,
metric/drawdown traceability to the results CSVs, and allocation blending.

Pure functions only - no Streamlit runtime needed.
"""
import pathlib
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import data as ad
from app import formatting as fmt

ROOT = pathlib.Path(__file__).resolve().parent.parent

requires_results = pytest.mark.skipif(
    not (ROOT / "results" / "tables" / "performance_metrics.csv").exists(),
    reason="results not generated yet (run scripts/run_part_b.py)",
)


@pytest.fixture(scope="module")
def app_data():
    return ad.build_app_data()


# ---------------------------------------------------------------------------
# Universe grouping (prompt_04: Equity 12 / Crypto 9 / Multi-Asset 5)
# ---------------------------------------------------------------------------

def test_universe_sizes(app_data):
    sizes = {u: len(f) for u, f in app_data.universe_funds.items()}
    assert sizes == {"Equity": 12, "Crypto": 9, "Multi-Asset": 5}


def test_universe_composition(app_data):
    assert app_data.universe_funds["Equity"] == [
        "equity_equal_weight", "equity_min_variance", "equity_max_sharpe",
        "equity_risk_parity",
        "defensive_equal_weight", "defensive_risk_parity",
        "cyclical_equal_weight", "cyclical_risk_parity",
        "growth_sensitive_equal_weight", "growth_sensitive_risk_parity",
        "equity_min_variance_momentum", "equity_min_variance_contrarian",
    ]
    assert app_data.universe_funds["Crypto"] == [
        "crypto_equal_weight", "crypto_min_variance", "crypto_max_sharpe",
        "crypto_risk_parity",
        "payments_equal_weight", "payments_risk_parity",
        "web3infra_equal_weight", "web3infra_risk_parity",
        "crypto_max_sharpe_vol_targeted",
    ]
    assert app_data.universe_funds["Multi-Asset"] == [
        "combined_equal_weight", "combined_min_variance",
        "combined_max_sharpe", "combined_risk_parity",
        "combined_max_sharpe_vol_targeted",
    ]


def test_universe_ids_are_disjoint(app_data):
    all_ids = [f for u in app_data.universe_funds.values() for f in u]
    assert len(all_ids) == len(set(all_ids)) == 26


def test_no_unclassified_funds(app_data):
    assert app_data.unclassified == []


def test_every_universe_fund_has_display_name(app_data):
    for u in ad.UNIVERSES:
        for fund in app_data.universe_funds[u]:
            name = app_data.lookup[fund]
            assert name not in fund  # never leak a raw fund id as a label
            assert name.startswith("Invesper")


def test_base_rows_excluded_from_universes(app_data):
    all_ids = {f for u in app_data.universe_funds.values() for f in u}
    assert not any(f.endswith("_base") for f in all_ids)


# ---------------------------------------------------------------------------
# Metrics: every universe fund traces to one of the three source CSVs
# ---------------------------------------------------------------------------

def test_metrics_cover_all_universe_funds(app_data):
    universe_ids = {f for u in app_data.universe_funds.values() for f in u}
    assert set(app_data.metrics["fund"]) == universe_ids


def test_metrics_sources(app_data):
    assert set(app_data.metrics["source"]) == {
        "results/tables/performance_metrics.csv",
        "results/tables/fusion_comparison.csv",
        "results/tables/vol_target_comparison.csv",
    }


def test_variant_metrics_from_comparison_csvs(app_data):
    row = app_data.metrics.set_index("fund")
    assert row.loc["equity_min_variance_momentum", "source"].endswith("fusion_comparison.csv")
    assert row.loc["crypto_max_sharpe_vol_targeted", "source"].endswith("vol_target_comparison.csv")


@requires_results
def test_drawdown_matches_performance_metrics(app_data):
    pm = pd.read_csv(ROOT / "results" / "tables" / "performance_metrics.csv")
    pm = pm.set_index("fund")
    for fund in ["combined_equal_weight", "crypto_max_sharpe", "equity_min_variance"]:
        series = ad.fund_return_series(app_data.returns, fund)
        assert series.index.is_monotonic_increasing
        recomputed = ad.drawdown_from_returns(series).min()
        assert recomputed == pytest.approx(pm.loc[fund, "max_drawdown"], abs=1e-4)


def test_variants_have_return_series_now(app_data):
    """Prompt_05: the 4 variants persist real daily returns in fund_returns.csv."""
    variants = ["equity_min_variance_momentum", "equity_min_variance_contrarian",
                "crypto_max_sharpe_vol_targeted", "combined_max_sharpe_vol_targeted"]
    for fund in variants:
        series = ad.fund_return_series(app_data.returns, fund)
        assert not series.empty, fund
        assert series.index.is_monotonic_increasing
        assert len(series) >= 200, fund
        assert series.index.min() <= pd.Timestamp("2021-01-05")


@requires_results
def test_variant_drawdown_matches_comparison_csvs(app_data):
    fc = pd.read_csv(ROOT / "results" / "tables" / "fusion_comparison.csv").set_index("fund")
    for fund in ["equity_min_variance_momentum", "equity_min_variance_contrarian"]:
        dd = ad.drawdown_from_returns(
            ad.fund_return_series(app_data.returns, fund)).min()
        assert dd == pytest.approx(fc.loc[fund, "max_drawdown"], abs=1e-4), fund

    vt = pd.read_csv(ROOT / "results" / "tables" / "vol_target_comparison.csv").set_index("fund")
    for fund in ["combined_max_sharpe_vol_targeted", "crypto_max_sharpe_vol_targeted"]:
        dd = ad.drawdown_from_returns(
            ad.fund_return_series(app_data.returns, fund)).min()
        assert dd == pytest.approx(vt.loc[fund, "max_drawdown"], abs=1e-4), fund


def test_allocation_includes_variants(app_data):
    assert "equity_min_variance_momentum" in app_data.allocation_funds
    assert "equity_min_variance_contrarian" in app_data.allocation_funds
    assert "combined_max_sharpe_vol_targeted" in app_data.allocation_funds
    assert "crypto_max_sharpe_vol_targeted" in app_data.allocation_funds
    assert len(app_data.allocation_funds) == 26


def test_fusion_variants_have_own_weights(app_data):
    """Fusion tilts reallocate monthly, so they publish their own weight rows."""
    for fund in ["equity_min_variance_momentum", "equity_min_variance_contrarian"]:
        holds, latest = ad.latest_holdings(app_data.weights, fund)
        assert latest is not None, fund
        assert holds["weight"].is_monotonic_decreasing
        assert holds["weight"].sum() == pytest.approx(1.0, abs=1e-4)


def test_vol_target_holdings_fall_back_to_base_fund(app_data):
    """Vol-targeted variants store no weight rows; holdings come from the base."""
    for fund, base in [("combined_max_sharpe_vol_targeted", "combined_max_sharpe"),
                       ("crypto_max_sharpe_vol_targeted", "crypto_max_sharpe")]:
        vt_holds, vt_latest = ad.latest_holdings(app_data.weights, fund)
        assert vt_holds.empty and vt_latest is None, fund
        base_holds, _ = ad.latest_holdings(app_data.weights, base)
        assert not base_holds.empty
        assert ad.base_fund_of(fund) == base


# ---------------------------------------------------------------------------
# Allocation blending
# ---------------------------------------------------------------------------

def test_blend_normalised_weights_make_full_growth(app_data):
    single_fund = "equity_equal_weight"
    single = ad.growth_of_1(ad.fund_return_series(app_data.returns, single_fund))
    g_single = ad.blend_portfolio(
        app_data.returns, [single_fund], {single_fund: 1.0}, 0.0
    )
    assert g_single["gross"].iloc[-1] == pytest.approx(single.iloc[-1], rel=1e-9)


def test_blend_fee_only_reduces_net(app_data):
    funds = ["equity_equal_weight", "crypto_equal_weight"]
    w = {"equity_equal_weight": 0.5, "crypto_equal_weight": 0.5}
    g0 = ad.blend_portfolio(app_data.returns, funds, w, 0.0)
    g1 = ad.blend_portfolio(app_data.returns, funds, w, 0.05)
    assert (g1["net"] <= g0["gross"]).all()
    assert g1["net"].iloc[-1] < g0["gross"].iloc[-1]


def test_blend_zero_fee_equals_gross(app_data):
    funds = ["equity_min_variance"]
    g = ad.blend_portfolio(app_data.returns, funds, {"equity_min_variance": 1.0}, 0.0)
    assert (g["net"] == g["gross"]).all()


# ---------------------------------------------------------------------------
# Sentiment
# ---------------------------------------------------------------------------

def test_market_sentiment_series(app_data):
    mk = ad.market_sentiment_series(app_data.sector)
    assert len(mk) == app_data.sector["date"].nunique()
    assert mk.index.is_monotonic_increasing


def test_gauge_scale_bounds(app_data):
    scaled = ad.rescale_0_100(app_data.market_sentiment)
    assert scaled.min() >= 0 and scaled.max() <= 100
    assert scaled.min() == pytest.approx(0.0)
    assert scaled.max() == pytest.approx(100.0)


def test_holdings_are_sorted_top_down(app_data):
    holds, latest = ad.latest_holdings(app_data.weights, "equity_equal_weight")
    assert latest is not None
    assert holds["weight"].is_monotonic_decreasing
    assert holds["weight"].sum() == pytest.approx(1.0, abs=1e-4)


# ---------------------------------------------------------------------------
# Per-fund management fees (prompt_06 item 6)
# ---------------------------------------------------------------------------

def test_fee_schedule_covers_every_allocation_fund(app_data):
    fees = app_data.fees
    assert set(fees) == set(app_data.allocation_funds)
    assert len(fees) == 26
    assert all(0.0 < v <= 0.01 for v in fees.values())
    # the priciest funds are the most "actively managed" variants
    assert fees["crypto_max_sharpe_vol_targeted"] == 0.0095
    assert fees["equity_min_variance_momentum"] == 0.0085
    assert fees["equity_equal_weight"] == 0.0005  # cheapest = passive index


def test_fee_schedule_matches_committed_csv(app_data):
    fees = ad.load_fund_fees()
    assert list(fees.columns) == ["fund_id", "fee_annual"]
    assert len(fees) == 26
    assert dict(zip(fees["fund_id"], fees["fee_annual"])) == app_data.fees


def test_blended_fee_weighted_average(app_data):
    fees = app_data.fees
    w = {"equity_equal_weight": 0.5, "crypto_equal_weight": 0.5}
    got = ad.blended_fee(w, fees)
    assert got == pytest.approx(0.5 * 0.0005 + 0.5 * 0.0025)
    # a variant-heavy allocation is genuinely pricier
    w2 = {"equity_min_variance_momentum": 1.0}
    assert ad.blended_fee(w2, fees) == pytest.approx(0.0085)


# ---------------------------------------------------------------------------
# Blended-portfolio metrics: empirical annualisation (prompt_06 correction)
# ---------------------------------------------------------------------------

def test_annualisation_factor_equity_blend_near_252(app_data):
    eq = ad.blend_portfolio(app_data.returns, ["equity_equal_weight"],
                            {"equity_equal_weight": 1.0}, 0.0)
    ann = ad.annualisation_factor(eq.index)
    assert ann == pytest.approx(252, rel=0.05)


def test_annualisation_factor_rises_with_crypto_weight(app_data):
    eq = ad.blend_portfolio(app_data.returns, ["equity_equal_weight"],
                            {"equity_equal_weight": 1.0}, 0.0)
    eq_ann = ad.annualisation_factor(eq.index)
    mix = ad.blend_portfolio(
        app_data.returns,
        ["equity_equal_weight", "crypto_equal_weight"],
        {"equity_equal_weight": 0.5, "crypto_equal_weight": 0.5}, 0.0)
    mix_ann = ad.annualisation_factor(mix.index)
    assert mix_ann > eq_ann  # crypto dates push the union calendar toward 365
    assert eq_ann <= mix_ann <= 370  # ~365 + calendar-span rounding (leap years)


def test_portfolio_metrics_use_observed_calendar(app_data):
    mix = ad.blend_portfolio(
        app_data.returns,
        ["equity_equal_weight", "crypto_equal_weight"],
        {"equity_equal_weight": 0.5, "crypto_equal_weight": 0.5}, 0.0)
    m = ad.portfolio_metrics(mix)
    assert set(m) == {"annualised_return", "annualised_volatility", "sharpe_ratio",
                      "max_drawdown", "total_return", "annualisation_factor"}
    assert m["annualisation_factor"] > 252  # crypto-inclusive, not flat 252
    ann = m["annualisation_factor"]
    r = mix["gross"].pct_change().dropna()
    assert m["annualised_return"] == pytest.approx(r.mean() * ann)
    assert m["annualised_volatility"] == pytest.approx(r.std(ddof=1) * (ann ** 0.5))
    assert m["sharpe_ratio"] == pytest.approx(
        m["annualised_return"] / m["annualised_volatility"])
    assert m["max_drawdown"] <= 0
    assert m["total_return"] == pytest.approx(float(mix["gross"].iloc[-1] - 1))


# ---------------------------------------------------------------------------
# App does not load the lexicon comparison summary (removed from the app)
# ---------------------------------------------------------------------------

def test_app_never_reads_lexicon_summary():
    """The lexicon comparison summary feature was removed from the app; the
    data layer must not resurrect a loader for it."""
    for rel in ("streamlit_app.py", "app/data.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "sentiment_lexicon_comparison_summary" not in src, rel
        assert "load_sentiment_lexicon_summary" not in src, rel
        assert "lexicon_summary" not in src, rel


@requires_results
def test_app_never_reads_headline_sentiment():
    for rel in ("streamlit_app.py", "app/data.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "headline_sentiment" not in src, rel


# ---------------------------------------------------------------------------
# Presentation formatting (prompt_06 items 1-2)
# ---------------------------------------------------------------------------

def test_format_date_long_form():
    assert fmt.format_date("2021-01-04") == "04 January 2021"
    assert fmt.format_date(pd.Timestamp("2021-01-04")) == "04 January 2021"
    assert fmt.format_date("2021-12-31") == "31 December 2021"


def test_metric_label_lookup():
    assert fmt.metric_label("sharpe_ratio") == "Sharpe Ratio"
    assert fmt.metric_label("max_drawdown") == "Max Drawdown"
    assert fmt.metric_label("annualised_return") == "Annualised Return"
    assert fmt.metric_label("annualised_volatility") == "Annualised Volatility"


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(pytest.main([__file__, "-q"]))
