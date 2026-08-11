# Prompt 03 — Investor-facing fund display names

The 22 base funds plus the fusion and vol-target variants currently only have
technical ids (`equity_max_sharpe`, etc.). Those ids stay exactly as they are
everywhere they currently matter — `parse_fund_id`, the `fund` column in
`fund_returns.csv`/`fund_weights.csv`/`performance_metrics.csv`, the prompt
logs, and every test. Do **not** rename any fund id. This prompt only adds a
separate, investor-facing **display name** layer used for anything a person
actually reads: figure titles/legends, the report (later), and the app
(later).

## 1. Add the mapping

Create `src/branding.py` with a single dict, `DISPLAY_NAMES`, mapping every
fund id (and the fusion/vol-target variant keys, however those are currently
identified in `fusion_comparison.csv` / `vol_target_comparison.csv`) to its
display name:

```python
DISPLAY_NAMES = {
    # Core 12
    "equity_equal_weight": "Invesper US Equity Index Fund",
    "equity_min_variance": "Invesper US Equity Minimum Volatility Fund",
    "equity_max_sharpe": "Invesper US Equity Opportunities Fund",
    "equity_risk_parity": "Invesper US Equity Balanced Risk Fund",
    "crypto_equal_weight": "Invesper Digital Assets Index Fund",
    "crypto_min_variance": "Invesper Digital Assets Minimum Volatility Fund",
    "crypto_max_sharpe": "Invesper Digital Assets Opportunities Fund",
    "crypto_risk_parity": "Invesper Digital Assets Balanced Risk Fund",
    "combined_equal_weight": "Invesper Multi-Asset Index Fund",
    "combined_min_variance": "Invesper Multi-Asset Minimum Volatility Fund",
    "combined_max_sharpe": "Invesper Multi-Asset Opportunities Fund",
    "combined_risk_parity": "Invesper Multi-Asset Balanced Risk Fund",
    # 5 groupings (10 funds)
    "defensive_equal_weight": "Invesper Defensive Sectors Index Fund",
    "defensive_risk_parity": "Invesper Defensive Sectors Balanced Risk Fund",
    "cyclical_equal_weight": "Invesper Cyclical Sectors Index Fund",
    "cyclical_risk_parity": "Invesper Cyclical Sectors Balanced Risk Fund",
    "growth_sensitive_equal_weight": "Invesper Growth & Innovation Sectors Index Fund",
    "growth_sensitive_risk_parity": "Invesper Growth & Innovation Sectors Balanced Risk Fund",
    "payments_equal_weight": "Invesper Digital Payments Index Fund",
    "payments_risk_parity": "Invesper Digital Payments Balanced Risk Fund",
    "web3infra_equal_weight": "Invesper Web3 Infrastructure Index Fund",
    "web3infra_risk_parity": "Invesper Web3 Infrastructure Balanced Risk Fund",
}

FUSION_DISPLAY_NAMES = {
    "momentum": "Invesper US Equity Minimum Volatility Fund (Momentum)",
    "contrarian": "Invesper US Equity Minimum Volatility Fund (Contrarian)",
}

VOL_TARGET_DISPLAY_NAMES = {
    "combined_max_sharpe": "Invesper Multi-Asset Opportunities Fund (Managed Vol)",
    "crypto_max_sharpe": "Invesper Digital Assets Opportunities Fund (Managed Vol)",
}
```

Adjust the fusion/vol-target dict keys to whatever the actual identifiers are
in those two CSVs/functions — check `src/fusion.py` and `src/vol_target.py`
for the real key names rather than assuming `"momentum"`/`"contrarian"` match
exactly.

Also write `results/data/fund_display_names.csv` (columns: `fund_id`,
`display_name`) generated from this dict, so Station 4 (the app, later) can
just read a lookup table instead of importing `src/branding.py` directly.
Regenerate this file as part of `scripts/run_part_b.py`'s normal run.

## 2. Apply it to every figure

Go through `src/plots.py` and use `DISPLAY_NAMES` (and the fusion/vol-target
dicts) wherever a fund id, family name, or method name is currently rendered
as human-readable text — legends, x-axis tick labels, chart titles, the
metrics-table figure's row labels. This includes at minimum:
`fig_sharpe_barplot`, `fig_growth_of_1`, `fig_metrics_table`,
`fig_growth_groupings`, `fig_fusion_growth`, `fig_vol_target_growth`,
`fig_vol_target_scaling`, and the weights-over-time / drawdown figures'
titles (those can keep referring to the underlying fund, just via its display
name instead of e.g. "Combined Maximum-Sharpe").

Don't change what the *source CSVs* look like (fund id stays the technical id
in `fund` columns) — this is purely a rendering-time lookup, so
`results/tables/lexicon_candidate_ledger.csv`-style traceability (every report
number traces to a CSV) still holds; the CSV is just not what a reader looks
at directly.

## 3. Regenerate and verify

- Run the full pipeline, regenerate every figure.
- Spot-check the actual rendered figures (not just "the code ran") — the
  Sharpe barplot and growth-of-$1 figures are the best places to confirm
  labels read correctly and aren't truncated/overlapping now that some names
  are longer than the old technical ids (e.g. "Invesper Web3 Infrastructure
  Balanced Risk Fund" is a lot longer than "web3infra_risk_parity" was as a
  label — check legend/axis sizing still looks clean, adjust font
  size/rotation/wrapping if needed).
- Run the test suite and ruff.

## 4. Document

- Add a new entry to `ai/prompt_log.md` in the existing format.
- Update `README.md` to mention `src/branding.py` and
  `results/data/fund_display_names.csv`, and note that fund ids remain the
  technical identifiers used throughout the codebase/CSVs — display names are
  a presentation-only layer.

Report back: confirmation every figure now shows display names correctly
(not truncated/overlapping), and the fund-id-to-display-name mapping is
available as both `src/branding.py` and `results/data/fund_display_names.csv`.
