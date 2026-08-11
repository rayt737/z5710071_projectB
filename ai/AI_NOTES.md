# AI_NOTES — how I directed and checked the AI

Short account of how I (the student) used the AI assistant on Stations 3-4,
what I checked, and where I overrode it. Full detail is in `ai/prompt_log.md`
(one numbered Entry per real problem, chronological).

## What I had AI do

- **Port Part A logic into Part B**: `src/etl.py` and `src/style.py` were
  copied and adapted; `src/features.py` was rebuilt (the headline-panel
  assembly was vectorised with `np.searchsorted` because the per-row loop the
  AI first produced would have been too slow on ~147k headlines).
- **Build the fund layer**: the four optimisers, the walk-forward expanding
  backtest, the metrics/turnover functions.
- **Build the sentiment layer**: VADER scoring, the LM-grounded lexicon
  extension, the sector index.
- **Build the fusion baseline** and wire everything into
  `scripts/run_part_b.py`.
- **Build the Station 4 app (first pass, prompt_04)**: a pure data layer in
  `app/data.py` (no streamlit imports) plus the five-section
  `streamlit_app.py`, all reading only the precomputed `results/` CSVs. Universe
  grouping (Equity 12 / Crypto 9 / Multi-Asset 5) is derived from the data, and
  every fund label is a display name from `results/data/fund_display_names.csv`.
- **Make the 4 extension variants fully interactive (prompt_05)**: appended
  their daily return series to `fund_returns.csv` and the fusion tilt weight
  series to `fund_weights.csv` (reordered `run_part_b.py` so the in-memory
  series are saved), made the fact sheets render real charts for all 26 funds,
  gave the vol-targeted variants a base-fund holdings fallback with an
  explanatory caption, added all 4 to the allocation picker, and added the
  gauge's unlagged/display-only caption. Logged in `ai/prompt_log.md` Entry 10.
- **Design/polish pass (prompt_06)**: long-form dates + humanised metric labels
  via one shared helper; horizontal sorted Sharpe chart; native Plotly
  VADER-vs-finVADER chart from a small precomputed summary CSV (no embedded PNG,
  no per-headline table in the app); the real 26-entry fee schedule replacing
  the editable fee input; and a fifth Portfolio tab (submit/save/list/delete
  session-only portfolios with donut + gross-vs-net growth + headline metrics).
  Logged in `ai/prompt_log.md` Entry 11.

## Where the AI was wrong and how I caught it (summary)

1. **Optimiser stall + silent collapse (biggest one).** SLSQP kept failing on
   the tiny daily-return covariances, and min-variance collapsed to exactly
   equal-weight because returns were scaled in two places (backtest AND
   optimiser). I had told the AI to add a pairwise-method-difference assertion
   precisely for this trap, and it fired. Fix: single scaling point inside the
   optimisers, analytic gradients, trust-constr fallback, warm-starts, clip +
   renormalise. Logged in `ai/prompt_log.md` Entry 1.
2. **Fund-id parsing.** `rsplit("_", 1)` on `equity_min_variance` returns the
   wrong family (`equity_min`). Caught while wiring the metrics table. Fix:
   `parse_fund_id` using `split("_", 1)` with validation. Logged in
   `ai/prompt_log.md` Entry 2.
3. **Two smaller runtime bugs** (weights index had no stable `date` name; a
   figure-period helper used `.index.min()` on a RangeIndex). Caught by the
   first full-pipeline runs. Logged in `ai/prompt_log.md` Entry 3.
4. **Lexicon candidate-count gap.** The Station-3 report mentioned 55 candidate
   terms but the extension CSV holds 37. Audit showed the "55" was a
   development-time partial-corpus count; on the full corpus the screen yields
   80, of which 21 were rated and 59 deliberately excluded (14 already in
   VADER, 45 by category), while 16 CSV terms were added by a documented
   manual-coverage step. Fix: a machine-checkable candidate ledger +
   `scripts/audit_lexicon_traceability.py`; no lexicon values changed, so no
   downstream re-run was needed. Logged in `ai/prompt_log.md` Entry 4.
5. **Figure captions: "Jan 1970" period + copy-pasted footer.** The drawdown
   figure's period helper read a float return as nanoseconds since epoch
   ("Jan 1970"), and a hardcoded "Returns are simple daily returns." footer
   was stamped on every figure — meaningless on the weights, lexicon and
   sector-index exhibits. Fix: the period helper now only accepts real dates,
   and every caption carries a figure-specific content line. All figures
   regenerated and verified by OCR of the rendered PNGs. Logged in
   `ai/prompt_log.md` Entry 5.
6. **prompt_02 extension: `growth_sensitive` broke fund-id parsing.** The
   Entry-2 `split("_", 1)` fix assumed only METHODS contain underscores; the
   new family id `growth_sensitive` does too, so
   `"growth_sensitive_equal_weight".split("_", 1)` split on the wrong side and
   raised. Caught by the caption test on the first run. Fix: rewrote
   `parse_fund_id` to infer the method by known-suffix matching (family-agnostic),
   replaced every other hardcoded split on fund ids, and added grouping + 
   vol-target tests. The 10 grouping funds (equal-weight/risk parity only) and
   the Moreira-Muir vol-targeting overlay were implemented and verified end to
   end. Logged in `ai/prompt_log.md` Entry 6.
7. **Vol-target target was look-ahead (bigger catch).** The target vol was the
   fund's FULL-SAMPLE realised vol over 2021-2023 — unknowable on any live day.
   During calm early-2021, the future-inflated target sat above trailing vol so
   k_t > 1 and the overlay leveraged up right before the 2022 crash (max DD
   -52.7% -> -59.3%). I flagged it as a "surprise"; a reviewer identified it as
   look-ahead. Fix: target = annualised vol of the fund's INITIAL ESTIMATION
   WINDOW ONLY (252/365 days, fixed once before live trading), the overlay runs
   on the fund's full history (first-rebalance weights x estimation-window
   returns + OOS returns), and `target_vol_of` asserts no date beyond the window
   contributes. Regression test added. Honest result: with a causal target the
   overlay does NOT help (Combined Sharpe 0.404 -> 0.307, max DD -66.96%;
   Crypto 0.462 -> 0.470, max DD -88.05%) — reported without tuning. Logged in
   `ai/prompt_log.md` Entry 7.
 8. **Station 4 (prompt_04) — a bug only reachable after user input.** Streamlit's
    AppTest caught it on the first run: the allocation slider loop labelled each
    slider `options[fund]`, but `options` maps display name -> id, so picking a
    fund raised `KeyError`. The default app view was fine — the crash only
    happened once a user actually selected funds. Fix + full detail (variant
    fact-sheet limitation, blend alignment, fee mechanics, gauge rescale) in
    `ai/prompt_log.md` Entry 9.
 9. **prompt_05 — the variants were only summary rows, not usable funds.** The
    fusion/vol-target daily series existed in memory but were never saved, so
    the app showed a "not published" note instead of charts. Fixed by appending
    the series to `fund_returns.csv` / `fund_weights.csv` and removing the
    special-case. My own first AppTest assertions were wrong too (expected the
    variant view to ADD charts, when it actually keeps the count equal to a
    base fund's) — the corrected test checks the count does NOT drop to the
    old 3-chart early-return behaviour. See `ai/prompt_log.md` Entry 10.
10. **prompt_06 — hardcoded 252 annualisation on a user-blended series.** I had
    annualised the Portfolio tab's blended gross/net series with the flat
    equity factor 252. The student correctly rejected this: `blend_portfolio`
    aligns funds on the UNION calendar, so a crypto-inclusive portfolio trades
    ~365 days/year and 252 understates annualised vol by ~20%, flattering the
    headline Sharpe for arbitrary mixes. Fix: derive the factor empirically
    per portfolio (`observed trading days / years spanned`) and state it in the
    caption; published fund metrics keep sqrt(252)/sqrt(365) per family. See
    `ai/prompt_log.md` Entry 11 (also: a 60-vs-61 histogram-count test slip,
    a duplicate-plotly-element guard, and a reused widget-key fix).

## How I checked the AI's output

- **Assertions in code** (no-look-ahead, long-only, sum=1, methods differ) plus
  a `tests/test_smoke.py` suite (24 tests) that re-checks them independently.
- **App tests**: `tests/test_app_data.py` (32 data-layer tests: universe
  composition, display-name coverage, drawdown/blend/gauge traceability to the
  CSVs, variant series/weights, fee schedule + blended fee, empirical
  annualisation + portfolio metrics, summary-CSV reproduction, no
  per-headline-table read) and `tests/test_app.py` (9 Streamlit AppTest smoke
  tests that run the real app headlessly and exercise all five tabs, including
  the portfolio save/list/delete flow). 65 tests total.
- **Hand checks**: verified one return by hand, confirmed the sector index is
  lagged exactly one trading day, confirmed the lexicon extension flips
  `upgrade`/`miss` headlines as intended.
- **Traceability**: every number in the report traces to a CSV under `results/`
  - I check figures are built from those CSVs, never from hand-computed values.
- **Full rerun**: `python scripts/run_part_b.py` from a clean checkout reproduces
  every output, then `python -m pytest -q tests/`.

## What I decided myself (AI applied it)

- Monthly rebalancing on the first trading day of each month; expanding window;
  initial window = first year (252/365). rf = 0. Carry-forward for no-news
  stock-days (not drop/neutral). 60-day z-score window for fusion; lambda
  untuned at +/-1. These are stated choices, not AI defaults.

## Honesty note

The AI wrote most of the production code and I reviewed/asserted it. The
two-pass lexicon ratings and every modelling choice above are mine; the AI
implemented the mechanics. Problems are logged in `ai/` as they happened, not
written up retroactively.
