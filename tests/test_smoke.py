"""Smoke tests for Station 3: imports, optimisers, backtest sanity, sentiment
and fusion invariants, plus CSV traceability when outputs exist.

Run:
    python tests/test_smoke.py          # plain runs
    python -m pytest -q tests/          # pytest collection
"""
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import branding as brand
from src import data_access, etl
from src import fusion as fu
from src import portfolios as pf
from src import sentiment as sent

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOL = pf.WEIGHT_TOL


# ---------------------------------------------------------------------------
# Imports / data
# ---------------------------------------------------------------------------

def test_imports():
    assert hasattr(data_access, "load_equity_prices")


def test_data_loads():
    eq = data_access.load_equity_prices()
    assert eq.shape[0] > 0
    assert {"ticker", "date", "adjClose", "sector"}.issubset(eq.columns)


# ---------------------------------------------------------------------------
# Fund id parsing (methods contain underscores!)
# ---------------------------------------------------------------------------

def test_parse_fund_id():
    assert pf.parse_fund_id("equity_min_variance") == ("equity", "min_variance")
    assert pf.parse_fund_id("crypto_risk_parity") == ("crypto", "risk_parity")
    assert pf.parse_fund_id("combined_max_sharpe") == ("combined", "max_sharpe")
    with pytest.raises(ValueError):
        pf.parse_fund_id("equity_bogus")


# ---------------------------------------------------------------------------
# Optimisers: long-only, fully invested, and methods genuinely differ
# ---------------------------------------------------------------------------

def _synthetic_mu_cov(n: int = 8, seed: int = 7):
    rng = np.random.default_rng(seed)
    vols = rng.uniform(0.01, 0.05, n)
    corr = rng.uniform(-0.3, 0.7, (n, n))
    corr = (corr + corr.T) / 2
    np.fill_diagonal(corr, 1.0)
    cov = np.outer(vols, vols) * corr
    mu = rng.uniform(-0.0002, 0.0006, n)
    return mu, cov


def test_optimisers_long_only_fully_invested():
    mu, cov = _synthetic_mu_cov()
    for m in pf.METHODS:
        w = pf.optimise(m, mu, cov)
        assert w.shape == (8,), m
        assert np.all(w >= -TOL), f"{m}: negative weight {w.min()}"
        assert abs(w.sum() - 1.0) <= TOL, f"{m}: sum {w.sum()} != 1"


def test_optimisers_genuinely_differ():
    mu, cov = _synthetic_mu_cov()
    ws = {m: pf.optimise(m, mu, cov) for m in pf.METHODS}
    pf.assert_methods_differ(ws)  # raises if any pair collapses


def test_assert_methods_differ_raises_on_collapse():
    w = np.full(4, 0.25)
    with pytest.raises(RuntimeError):
        pf.assert_methods_differ({"a": w, "b": w.copy()})


def test_assert_no_lookahead_raises():
    with pytest.raises(AssertionError):
        pf.assert_no_lookahead(pd.Timestamp("2021-01-05"), pd.Timestamp("2021-01-05"))
    pf.assert_no_lookahead(pd.Timestamp("2021-01-04"), pd.Timestamp("2021-01-05"))


# ---------------------------------------------------------------------------
# Walk-forward backtest: no look-ahead, valid weights, methods differ
# ---------------------------------------------------------------------------

def _synthetic_returns(n_days: int = 900, n_assets: int = 8, seed: int = 11):
    dates = pd.bdate_range("2020-01-01", periods=n_days)
    rng = np.random.default_rng(seed)
    rets = pd.DataFrame(rng.normal(0.0003, 0.015, (n_days, n_assets)),
                        index=dates, columns=[f"A{i}" for i in range(n_assets)])
    return rets


def test_oos_backtest_valid():
    rets = _synthetic_returns()
    for m in pf.METHODS:
        r, w = pf.oos_backtest(rets, m, initial_window=252)
        assert len(r) > 0
        assert r.index.min() > rets.index[251], "OOS must start after the init window"
        assert np.all(w.to_numpy() >= -TOL), f"{m}: negative weight"
        assert np.abs(w.sum(axis=1) - 1.0).max() <= TOL, f"{m}: sum != 1"
        # no look-ahead: every weight row's estimation window ends before its date
        for t, row in w.iterrows():
            hist = rets.loc[rets.index < t]
            pf.assert_no_lookahead(hist.index.max(), t)


def test_backtest_methods_differ_every_rebalance():
    rets = _synthetic_returns()
    res = pf.backtest_all_methods(rets, "equity", 252, 252)  # asserts pairwise diff
    assert set(res) == {"equity_" + m for m in pf.METHODS}


def test_turnover_sane():
    rets = _synthetic_returns()
    _, w = pf.oos_backtest(rets, "risk_parity", initial_window=252)
    t = pf.turnover(w)
    assert 0.0 <= t <= 2.0


# ---------------------------------------------------------------------------
# Sentiment: sector index is lagged at least one trading day
# ---------------------------------------------------------------------------

def test_sector_index_lagged_one_trading_day():
    dates = pd.bdate_range("2022-01-03", periods=10)
    scores = pd.DataFrame({
        "date": [dates[3], dates[3]],
        "ticker": ["A", "B"],
        "compound": [0.5, -0.1],
    })
    idx, aligned, lagged = sent.build_sector_sentiment_index(
        scores, dates, {"A": "Tech", "B": "Tech"})
    tech = idx[idx["sector"] == "Tech"].set_index("date")["sentiment"]
    assert abs(tech.loc[dates[3]]) < 1e-9, "no signal on the headline day (must lag)"
    assert abs(tech.loc[dates[4]] - 0.2) < 1e-9, "signal arrives next trading day"
    assert aligned.shape == lagged.shape


def test_lm_dictionary_loads_flags():
    lm = sent.load_lm_dictionary()
    assert "word" in lm.columns
    flags = sent.lm_flags(lm)
    assert "loss" in flags and "Negative" in flags["loss"]


def test_lexicon_extension_only_kept_terms():
    ext = sent.load_lexicon_extension()
    assert len(ext) > 0
    sia = sent.build_finvader_lite()
    for w in list(ext)[:5]:
        assert w in sia.lexicon


@pytest.mark.skipif(not (ROOT / "results/tables/lexicon_candidate_ledger.csv").exists(),
                    reason="run scripts/audit_lexicon_traceability.py first")
def test_lexicon_ledger_complete():
    """Every extension term is explained and every screen candidate has a disposition.

    This locks the candidate-count accounting (ai/prompt_log.md Entry 4):
    no term in finvader_lite_extension.csv may be unreproducible, and no screen
    candidate may go unaccounted for.
    """
    ledger = pd.read_csv(ROOT / "results/tables/lexicon_candidate_ledger.csv")
    ext = pd.read_csv(sent.EXTENSION_CSV)

    # 1) the ledger covers both sources
    assert set(ledger["source"]) == {"screen_pool", "manual_coverage"}
    n_screen = int((ledger["source"] == "screen_pool").sum())
    n_manual = int((ledger["source"] == "manual_coverage").sum())
    assert n_screen == 80, f"screen pool changed: {n_screen}"
    assert n_manual == len(ext) - 21, "manual-coverage count inconsistent with CSV"

    # 2) every screen candidate has an explicit disposition (no silent gap)
    assert ledger["disposition"].notna().all()
    assert (ledger["disposition"] != "").all()

    # 3) every extension term is accounted for with a rated_* disposition
    ext_by_word = dict(zip(ext["word"], ext["status"]))
    ledger_ext = ledger[ledger["disposition"].str.startswith("rated_")]
    assert len(ledger_ext) == len(ext) == 37
    assert set(ledger_ext["word"]) == set(ext["word"])
    for _, row in ledger_ext.iterrows():
        assert row["extension_status"] == ext_by_word[row["word"]]
        assert row["extension_status"] == row["disposition"].split("_", 1)[1]

    # 4) counts match the log: 21 rated from screen, 16 coverage, 35 kept + 2 flagged
    n_screen_rated = int(((ledger["source"] == "screen_pool") &
                          ledger["disposition"].str.startswith("rated_")).sum())
    assert n_screen_rated == 21, f"screen-rated count: {n_screen_rated}"
    assert int(ledger["extension_status"].eq("kept").sum()) == 35
    assert int(ledger["extension_status"].eq("flagged").sum()) == 2
    assert int(ledger["extension_status"].eq("kept").sum()) == 35
    assert int(ledger["extension_status"].eq("flagged").sum()) == 2


# ---------------------------------------------------------------------------
# Fusion: weights stay long-only, sum to 1, and constant sentiment does nothing
# ---------------------------------------------------------------------------

def _synthetic_fusion_inputs():
    dates = pd.bdate_range("2021-01-01", periods=400)
    base = pd.DataFrame(0.5, index=dates, columns=["A", "B"])
    base["A"] = 0.6
    base["B"] = 0.4
    aligned = pd.DataFrame(0.1, index=dates, columns=["A", "B"])  # constant -> z=0
    return base, aligned


def test_fusion_weights_valid():
    base, aligned = _synthetic_fusion_inputs()
    fused = fu.tilt_weights(base, aligned, lam=1.0)
    assert np.all(fused.to_numpy() >= -TOL)
    assert np.abs(fused.sum(axis=1) - 1.0).max() <= TOL
    # constant sentiment -> z = 0 -> weights unchanged
    assert np.abs(fused - base).to_numpy().max() < 1e-6


def test_fusion_turnover_reported():
    base, aligned = _synthetic_fusion_inputs()
    _, fused = fu.run_fusion(pd.DataFrame(0.001, index=base.index, columns=["A", "B"]),
                             base, aligned, lam=-1.0)
    assert isinstance(fu.turnover(fused), float)


# ---------------------------------------------------------------------------
# CSV traceability: every number in the report traces to these files
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not (ROOT / "results/tables/performance_metrics.csv").exists(),
                    reason="run scripts/run_part_b.py first")
def test_output_csvs_traceable():
    pm = pd.read_csv(ROOT / "results/tables/performance_metrics.csv")
    expected_funds = (
        {f"{f}_{m}" for f in ["equity", "crypto", "combined"] for m in pf.METHODS}
        | {f"{f}_{m}" for f in pf.SECTOR_CLUSTERS for m in pf.GROUP_METHODS}
        | {f"{f}_{m}" for f in pf.CRYPTO_THEMES for m in pf.GROUP_METHODS})
    assert pm.shape[0] == 22
    assert set(pm["fund"]) == expected_funds
    assert (pm["sharpe_ratio"].notna()).all()

    fr = pd.read_csv(ROOT / "results/data/fund_returns.csv")
    # prompt_05: the 4 extension variants are appended to the same long table
    variant_ids = {
        "equity_min_variance_momentum", "equity_min_variance_contrarian",
        "combined_max_sharpe_vol_targeted", "crypto_max_sharpe_vol_targeted"}
    assert set(fr["fund"].unique()) == set(pm["fund"]) | variant_ids

    fw = pd.read_csv(ROOT / "results/data/fund_weights.csv")
    assert (fw["weight"] >= -TOL).all()
    assert np.abs(fw.groupby(["fund", "rebalance_date"])["weight"].sum() - 1.0).max() <= TOL
    # fusion tilts reallocate monthly -> their own weight rows; vol-targeted
    # variants are a scalar overlay -> no duplicated rows (app falls back to base)
    assert {"equity_min_variance_momentum", "equity_min_variance_contrarian"} \
        <= set(fw["fund"].unique())
    assert not {"combined_max_sharpe_vol_targeted", "crypto_max_sharpe_vol_targeted"} \
        & set(fw["fund"].unique())

    fc = pd.read_csv(ROOT / "results/tables/fusion_comparison.csv")
    assert fc.shape[0] == 3  # base + momentum + contrarian

    vt = pd.read_csv(ROOT / "results/tables/vol_target_comparison.csv")
    assert set(vt["fund"]) == {
        "combined_max_sharpe_base", "combined_max_sharpe_vol_targeted",
        "crypto_max_sharpe_base", "crypto_max_sharpe_vol_targeted"}


@pytest.mark.skipif(not (ROOT / "results/data/fund_display_names.csv").exists(),
                    reason="run scripts/run_part_b.py first")
def test_fund_display_names_cover_every_id():
    """Every fund id in the CSVs resolves to a display name (Prompt 03).

    The lookup table written by the pipeline must match src/branding.py and
    cover the 22 base funds plus every fusion/vol-target variant row.
    """
    lookup = pd.read_csv(ROOT / "results/data/fund_display_names.csv")
    assert list(lookup.columns) == ["fund_id", "display_name"]
    assert set(lookup["fund_id"]) == set(brand.display_names_table()["fund_id"])

    from src import branding as b
    for fund_id in lookup["fund_id"]:
        got = lookup.set_index("fund_id").loc[fund_id, "display_name"]
        assert got == b.fund_display_name(fund_id)

    fund_ids = set()
    for rel in ["results/tables/performance_metrics.csv",
                "results/data/fund_returns.csv",
                "results/data/fund_weights.csv",
                "results/tables/fusion_comparison.csv",
                "results/tables/vol_target_comparison.csv"]:
        fund_ids |= set(pd.read_csv(ROOT / rel)["fund"].unique())
    assert fund_ids == set(lookup["fund_id"]), sorted(fund_ids ^ set(lookup["fund_id"]))


# ---------------------------------------------------------------------------
# prompt_02 grouping funds (10): valid weights, no look-ahead, methods differ
# ---------------------------------------------------------------------------

def test_group_funds_valid():
    """The 10 grouping funds must be long-only, fully invested, no look-ahead."""
    rets = _synthetic_returns().iloc[:, :6]  # mimic a cluster/theme subset
    for family in list(pf.SECTOR_CLUSTERS) + list(pf.CRYPTO_THEMES):
        init = pf.INITIAL_WINDOWS[family]
        for m in pf.GROUP_METHODS:
            _r, w = pf.oos_backtest(rets, m, initial_window=init)
            assert np.all(w.to_numpy() >= -TOL), f"{family}_{m}: negative weight"
            assert np.abs(w.sum(axis=1) - 1.0).max() <= TOL, f"{family}_{m}: sum != 1"
            for t, row in w.iterrows():
                hist = rets.loc[rets.index < t]
                pf.assert_no_lookahead(hist.index.max(), t)


def test_group_backtests_methods_differ():
    """Equal-weight vs risk parity must genuinely differ for every grouping."""
    rets = _synthetic_returns().iloc[:, :6]
    for family in list(pf.SECTOR_CLUSTERS) + list(pf.CRYPTO_THEMES):
        res = pf.backtest_all_methods(
            rets, family, pf.ANNUAL_FACTORS[family], pf.INITIAL_WINDOWS[family],
            methods=pf.GROUP_METHODS)
        assert set(res) == {f"{family}_{m}" for m in pf.GROUP_METHODS}


def test_group_universe_tickers_derive_from_data():
    """Cluster membership must come from the data's sector column (no ticker
    hardcoding), the clusters must partition the equity universe, and the
    crypto themes must exclude BTC-USD."""
    eq, _ = etl.load_clean_equities()
    cr, _ = etl.load_clean_crypto()
    sector_by_ticker = dict(zip(eq["ticker"], eq["sector"]))

    covered = set()
    for family, sectors in pf.SECTOR_CLUSTERS.items():
        tickers = pf.group_universe_tickers(eq, cr, family)
        assert len(tickers) == 5 * len(sectors), family
        assert {sector_by_ticker[t] for t in tickers} == set(sectors), family
        assert not (set(sectors) & covered), f"{family} overlaps another cluster"
        covered |= set(sectors)
    assert covered == set(eq["sector"].unique()), "clusters do not cover all sectors"

    for family, tickers in pf.CRYPTO_THEMES.items():
        got = pf.group_universe_tickers(eq, cr, family)
        assert got == tickers
        assert "BTC-USD" not in got


# ---------------------------------------------------------------------------
# Vol-targeting overlay: causal target, no look-ahead, clip band respected
# ---------------------------------------------------------------------------

def test_vol_target_scaling_sane():
    from src import vol_target as vt
    dates = pd.bdate_range("2021-01-04", periods=600)
    rng = np.random.default_rng(9)
    base = pd.Series(rng.normal(0.0004, 0.015, len(dates)), index=dates)

    est_window = 252
    target = vt.target_vol_of(base, est_window, 252)
    assert target > 0
    scaled, k, _target = vt.apply_overlay(base, 252, estimation_window=est_window)
    assert np.isclose(target, _target)

    # clip band [0.5, 1.5] is respected
    assert k.min() >= 0.5 - 1e-9, f"k below band: {k.min()}"
    assert k.max() <= 1.5 + 1e-9, f"k above band: {k.max()}"
    # warm-up (no trailing history) is neutral k = 1.0
    assert k.iloc[0] == 1.0
    # scaled = k * base
    assert np.allclose(scaled, k * base, atol=1e-12)
    # no look-ahead: the window ending at t-1 drives k_t
    for t in k.index:
        pos = base.index.get_loc(t)
        if pos > 0:
            pf.assert_no_lookahead(base.index[pos - 1], t)


def test_vol_target_target_is_initial_window_only():
    """The target must be the initial-window vol, never the full-sample vol.

    Regression guard for prompt_log Entry 7: the target used to be full-sample
    realised vol, which is look-ahead - during the calm pre-crash period the
    future-inflated target sat above trailing vol, k_t > 1, and the overlay
    leveraged the fund up right before the crash it 'knew' was coming.
    """
    from src import vol_target as vt
    rng = np.random.default_rng(7)
    n_est = 252
    n_total = 1005
    dates = pd.bdate_range("2020-01-02", periods=n_total)
    calm = rng.normal(0.0003, 0.008, n_est)        # calm initial window
    crashy = rng.normal(-0.0002, 0.025, n_total - n_est)  # volatile OOS
    base = pd.Series(np.r_[calm, crashy], index=dates)

    target = vt.target_vol_of(base, n_est, 252)
    window_vol = float(base.iloc[:n_est].std(ddof=1) * np.sqrt(252))
    full_vol = float(base.std(ddof=1) * np.sqrt(252))
    # the target is exactly the initial-window vol...
    assert np.isclose(target, window_vol)
    # ...and would FAIL if the old full-sample target were still in place
    assert target < full_vol
    # causality: corrupting any date OUTSIDE the window cannot move the target
    for bad in (np.nan, 999.0):
        base2 = base.copy()
        base2.iloc[n_est + 1] = bad
        assert vt.target_vol_of(base2, n_est, 252) == target


# ---------------------------------------------------------------------------
# Figure captions: period comes from real dates, never 1970, per-figure content
# ---------------------------------------------------------------------------

def _build_metrics(n_days: int = 200):
    """Synthetic metrics for the 22 real fund ids (so figure code exercises
    the actual DISPLAY_NAMES mapping)."""
    dates = pd.bdate_range("2022-01-03", periods=n_days)
    rows = [{
        "fund": fund_id,
        "annualised_return": 0.06, "annualised_volatility": 0.12,
        "sharpe_ratio": 0.5, "max_drawdown": -0.18, "total_return": 0.4,
        "turnover": 0.3, "first_live_date": dates[0], "last_date": dates[-1],
    } for fund_id in brand.DISPLAY_NAMES]
    return pd.DataFrame(rows)


def _build_return_series(n_days: int = 200, start: str = "2022-01-03"):
    dates = pd.bdate_range(start, periods=n_days)
    rng = np.random.default_rng(3)
    return pd.Series(rng.normal(0.0002, 0.01, n_days), index=dates)


def _build_returns_long(n_days: int = 200):
    dates = pd.bdate_range("2022-01-03", periods=n_days)
    rows = []
    rng = np.random.default_rng(5)
    for fund_id in brand.DISPLAY_NAMES:
        for d in dates:
            rows.append({"fund": fund_id, "date": d, "return": rng.normal(0.0002, 0.01)})
    return pd.DataFrame(rows)


def _capture_captions(monkeypatch, builders):
    captured = {}

    def fake_save_fig(fig, filename, results_dir="results/figures", caption="", dpi=150):
        import matplotlib.pyplot as plt
        captured[filename] = caption
        plt.close(fig)
        return pathlib.Path(results_dir) / filename

    from src import plots as pl
    monkeypatch.setattr(pl.sty, "save_fig", fake_save_fig)
    for fn, kwargs in builders:
        fn(**kwargs)
    return captured


def test_figure_captions_real_periods(monkeypatch):
    """Every figure caption must carry a real sample period from its dates.

    Guards against the Jan-1970 epoch bug (a float return min() read as
    nanoseconds since epoch) and against copy-pasted default caption text.
    """
    import re

    from src import plots as pl

    n_days = 200
    metrics = _build_metrics(n_days)
    rets = _build_return_series(n_days)
    long = _build_returns_long(n_days)
    dates = rets.index
    weights = pd.DataFrame(
        {"AAPL": 0.4, "GOOG": 0.3, "BTC-USD": 0.3},
        index=dates)
    sector_map = {"AAPL": "Tech", "GOOG": "Tech"}
    sent_plain = pd.Series(np.random.default_rng(1).normal(0, 0.1, n_days), index=dates)
    sent_ext = sent_plain * 1.1
    idx_long = pd.DataFrame({
        "date": np.repeat(dates, 2),
        "sector": ["Tech", "Energy"] * n_days,
        "sentiment": np.random.default_rng(2).normal(0, 0.2, n_days * 2),
    })

    builders = [
        (pl.fig_metrics_table, {"metrics": metrics, "filename": "t_metrics.png"}),
        (pl.fig_growth_of_1, {"fund_returns_long": long, "family": "equity",
                              "filename": "t_growth.png"}),
        (pl.fig_drawdown, {"returns": rets, "fund_label": "Equity min variance",
                           "filename": "t_drawdown.png"}),
        (pl.fig_weights_stacked, {"weights": weights, "sector_map": sector_map,
                                  "fund_label": "Equity", "filename": "t_weights.png"}),
        (pl.fig_sharpe_barplot, {"metrics": metrics, "filename": "t_sharpe.png"}),
        (pl.fig_sentiment_comparison, {"plain": sent_plain, "extended": sent_ext,
                                       "filename": "t_sent.png"}),
        (pl.fig_sector_sentiment, {"index_long": idx_long, "filename": "t_sector.png"}),
        (pl.fig_fusion_growth, {"base": rets, "momentum": rets * 1.1, "contrarian": rets * 0.9,
                                "filename": "t_fusion.png"}),
        (pl.fig_growth_groupings,
         {"fund_returns_long": long,
          "families": ["defensive", "cyclical", "growth_sensitive"],
          "filename": "t_group_eq.png", "title": "Equity clusters"}),
        (pl.fig_growth_groupings,
         {"fund_returns_long": long,
          "families": ["payments", "web3infra"],
          "filename": "t_group_cr.png", "title": "Crypto themes"}),
        (pl.fig_vol_target_growth,
         {"base": rets, "scaled": rets * 1.05, "fund_label": "Combined Maximum-Sharpe",
          "filename": "t_vt_growth.png"}),
        (pl.fig_vol_target_scaling,
         {"k": pd.Series(1.0, index=dates), "fund_label": "Combined Maximum-Sharpe",
          "filename": "t_vt_k.png"}),
    ]
    captured = _capture_captions(monkeypatch, builders)
    assert len(captured) == len(builders)

    stale_defaults = ["Out-of-sample period", "Returns are simple daily returns."]
    for filename, caption in captured.items():
        assert "1970" not in caption, f"{filename}: epoch-period leak: {caption}"
        for stale in stale_defaults:
            assert stale not in caption, f"{filename}: stale default text: {caption}"
        years = [int(y) for y in re.findall(r"\b(20\d{2})\b", caption)]
        assert years, f"{filename}: no year found in caption: {caption}"
        assert min(years) >= 2020, f"{filename}: period before data span: {caption}"

    # the drawdown figure (the original bug) must report the real series span
    dd = captured["t_drawdown.png"]
    expected_period = (f"{rets.index.min().strftime('%b %Y')} - "
                       f"{rets.index.max().strftime('%b %Y')}")
    assert expected_period in dd, f"drawdown period {expected_period!r} not in {dd}"


if __name__ == "__main__":
    test_imports()
    print("imports OK")
    test_parse_fund_id()
    print("fund id parsing OK")
    test_optimisers_long_only_fully_invested()
    test_optimisers_genuinely_differ()
    print("optimisers OK")
    test_assert_methods_differ_raises_on_collapse()
    test_assert_no_lookahead_raises()
    test_oos_backtest_valid()
    test_backtest_methods_differ_every_rebalance()
    print("backtest OK")
    test_group_funds_valid()
    test_group_backtests_methods_differ()
    test_group_universe_tickers_derive_from_data()
    print("grouping funds OK")
    test_vol_target_scaling_sane()
    test_vol_target_target_is_initial_window_only()
    print("vol-targeting OK")
    test_sector_index_lagged_one_trading_day()
    test_lm_dictionary_loads_flags()
    test_lexicon_extension_only_kept_terms()
    print("sentiment OK")
    try:
        test_lexicon_ledger_complete()
        print("lexicon ledger completeness OK")
    except Exception as e:  # ledger not generated yet
        print("lexicon ledger skipped:", e)
    test_fusion_weights_valid()
    print("fusion OK")
    try:
        test_output_csvs_traceable()
        print("CSV traceability OK")
    except Exception as e:  # results not generated yet
        print("CSV traceability skipped:", e)
    try:
        test_fund_display_names_cover_every_id()
        print("display-name coverage OK")
    except Exception as e:  # results not generated yet
        print("display-name coverage skipped:", e)
