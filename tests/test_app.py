"""Station 4 app smoke tests via streamlit.testing.v1.AppTest.

Exercises every tab (Streamlit renders all tabs eagerly, so a single run hits
all five sections) plus interactive flows: switching compare universes, opening
a variant fact sheet, building an allocation with schedule-driven fees, and the
Portfolio tab's submit/save/list/delete flow.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from streamlit.testing.v1 import AppTest

ROOT = pathlib.Path(__file__).resolve().parent.parent

APP = str(ROOT / "streamlit_app.py")

pytestmark = pytest.mark.skipif(
    not (ROOT / "results" / "tables" / "performance_metrics.csv").exists(),
    reason="results not generated yet (run scripts/run_part_b.py)",
)


def _app():
    return AppTest.from_file(APP).run()


def test_app_loads_all_five_tabs():
    at = _app()
    assert not at.exception
    assert at.title[0].value == "Invesper Systematic Funds"
    assert [t.label for t in at.tabs] == [
        "Compare funds", "Fund fact sheet", "Sentiment analytics",
        "Build an allocation", "Portfolio",
    ]
    assert len(at.dataframe) >= 1  # compare metrics table
    assert len(at.get("plotly_chart")) >= 6  # all sections render native charts
    # the only image is the Invesper logo beside the page title
    assert len(at.get("imgs")) == 1


def test_compare_switches_universe():
    at = _app()
    at.radio(key="cmp_universe").set_value("Crypto").run()
    assert not at.exception
    at.radio(key="cmp_universe").set_value("Multi-Asset").run()
    assert not at.exception


def test_fact_sheet_vol_target_variant_renders_charts_and_base_holdings():
    """Prompt_05: vol-targeted variants now have real charts + base-fund holdings."""
    at = _app()
    base_plotly = len(at.get("plotly_chart"))
    at.radio(key="fs_universe").set_value("Crypto").run()
    assert not at.exception
    at.selectbox(key="fs_fund").set_value(
        "Invesper Digital Assets Opportunities Fund (Managed Vol)"
    ).run()
    assert not at.exception
    assert not any("daily return history is not published" in i.value for i in at.info)
    # the variant now renders the same fact-sheet charts as a base fund
    # (growth + drawdown + holdings), so the total chart count is unchanged
    assert len(at.get("plotly_chart")) >= base_plotly
    assert any("Current holdings" in m.value for m in at.markdown)
    assert any(
        "scales overall exposure, not individual holdings" in c.value
        for c in at.caption
    )


def test_fact_sheet_fusion_variant_renders_charts():
    """Prompt_05: fusion variants now render growth/drawdown/holdings like any fund."""
    at = _app()
    base_plotly = len(at.get("plotly_chart"))
    at.selectbox(key="fs_fund").set_value(
        "Invesper US Equity Minimum Volatility Fund (Momentum)"
    ).run()
    assert not at.exception
    assert len(at.get("plotly_chart")) >= base_plotly
    assert any("Current holdings" in m.value for m in at.markdown)


def test_fact_sheet_base_fund_renders_charts():
    at = _app()
    assert not at.exception
    base_plotly = len(at.get("plotly_chart"))
    at.radio(key="fs_universe").set_value("Multi-Asset").run()
    assert not at.exception
    at.selectbox(key="fs_fund").set_value("Invesper Multi-Asset Index Fund").run()
    assert not at.exception
    # growth + drawdown + holdings render for a base fund and period captions present
    assert len(at.get("plotly_chart")) >= base_plotly
    assert any("2021" in c.value for c in at.caption)  # period captions present


def test_allocation_blends_gross_vs_net():
    at = _app()
    base_plotly = len(at.get("plotly_chart"))
    ms = at.multiselect(key="alloc_funds")
    ms.select("Invesper US Equity Index Fund").select("Invesper Digital Assets Index Fund").run()
    assert not at.exception
    assert len(at.slider) == 2
    at.slider(key="alloc_w_equity_equal_weight").set_value(60.0).run()
    at.slider(key="alloc_w_crypto_equal_weight").set_value(40.0).run()
    assert not at.exception
    assert len(at.get("plotly_chart")) > base_plotly  # blended growth chart added
    assert len(at.number_input) == 0  # prompt_06: the editable fee input is gone
    # per-fund fees next to each weight slider + weighted blended fee
    assert any("Fee: 0.05% p.a." in c.value for c in at.caption)
    assert any("Fee: 0.25% p.a." in c.value for c in at.caption)
    assert any("Blended management fee: 0.13% p.a." in m.value for m in at.markdown)
    assert any("Gross: $" in c.value for c in at.caption)


def test_allocation_includes_variant_funds():
    """Prompt_05: fusion and vol-targeted variants are selectable in the builder."""
    at = _app()
    base_plotly = len(at.get("plotly_chart"))
    ms = at.multiselect(key="alloc_funds")
    ms.select("Invesper US Equity Minimum Volatility Fund (Momentum)").select(
        "Invesper Digital Assets Opportunities Fund (Managed Vol)"
    ).run()
    assert not at.exception
    assert len(at.slider) == 2
    assert len(at.get("plotly_chart")) > base_plotly  # blended growth chart added


def test_sentiment_gauge_caption_present():
    """Prompt_05: the gauge must state it is unlagged and display-only."""
    at = _app()
    assert not at.exception
    assert any(
        "Current reading (unlagged)" in c.value for c in at.caption
    )


def test_portfolio_save_list_delete_flow():
    """Prompt_06 item 7: submit saves a copy in session_state; Portfolio tab
    lists it with the blended fee and an observed-calendar annualisation
    caption; delete removes it."""
    at = _app()
    ms = at.multiselect(key="alloc_funds")
    ms.select("Invesper US Equity Index Fund").run()
    assert not at.exception
    at.slider(key="alloc_w_equity_equal_weight").set_value(100.0).run()
    assert not at.exception
    at.button(key="alloc_submit").click().run()
    assert not at.exception
    assert at.session_state["saved_portfolios"][0]["name"] == "Portfolio 1"
    # Portfolio tab (rendered eagerly) shows the saved portfolio
    assert any("Invesper US Equity Index Fund (100%)" in m.value for m in at.markdown)
    assert any("Blended management fee: 0.05% p.a." in c.value for c in at.caption)
    assert any("observed trading calendar" in c.value for c in at.caption)
    # duplicate names auto-uniquify
    ms = at.multiselect(key="alloc_funds")
    ms.select("Invesper US Equity Index Fund").run()
    assert not at.exception
    at.slider(key="alloc_w_equity_equal_weight").set_value(100.0).run()
    assert not at.exception
    at.button(key="alloc_submit").click().run()
    assert not at.exception
    assert [p["name"] for p in at.session_state["saved_portfolios"]] == [
        "Portfolio 1", "Portfolio 2",
    ]
    # delete the second portfolio
    at.button(key="pf_del_Portfolio 2").click().run()
    assert not at.exception
    assert [p["name"] for p in at.session_state["saved_portfolios"]] == ["Portfolio 1"]
