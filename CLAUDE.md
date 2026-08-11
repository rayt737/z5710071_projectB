# CLAUDE.md - agent instructions for this project

## What this is

FINS3645 FinTech Project, Part B (DFF Stations 3-4), folder `z5710071_projectB`.
Station 3 (funds + sentiment + fusion) is complete; Station 4 (Streamlit app)
is built (five sections - Compare, Fact sheet, Sentiment, Allocation,
Portfolio - reading `results/` only; see `ai/prompts/prompt_04.md`,
`ai/prompts/prompt_05.md`, `ai/prompts/prompt_06.md`, `ai/prompt_log.md`
Entries 9-11). The 4
extension variants now have real daily series + fusion weight rows appended to
`results/` (vol-targeted variants inherit their base fund's holdings). Read, in
order: `PROJECT_BRIEF.md`, `ai/prompts/prompt_01.md`, `context/DATA_GUIDE.md`,
`context/project_context.md`.

Data comes from `src/data_access.py` (provided/frozen; Google-Drive zip, cached
after one hit; `FINS_DATA_ZIP` env var can point to a local zip). Never commit
raw data. All generated outputs go under `results/` and ARE committed.

## Non-negotiable coding rules (from ai/prompts/prompt_01.md)

- **No look-ahead, anywhere.** Weights on day *t* from data strictly before *t*;
  sentiment lagged >= 1 trading day. Enforce with explicit
  `assert_no_lookahead` assertions - never rely on careful indexing alone.
- **Long-only, fully invested.** Every fund's weights are `>= 0` and sum to 1
  at every rebalance. Assert it; tests in `tests/test_smoke.py`.
- Annualise equity/combined with sqrt(252), crypto with sqrt(365). Returns are
  computed within each panel first; combined = crypto returns left-merged onto
  the equity calendar. Risk-free rate = 0 (stated). EXCEPTION: the app's
  Portfolio tab blends funds on the union calendar, so its headline metrics are
  annualised on the blend's OWN observed calendar (`observed days / years
  spanned`, `app.data.annualisation_factor`) and the factor is shown in the UI
  caption - never hardcode 252 there (see `ai/prompt_log.md` Entry 11).
- The four optimisers must produce pairwise-different weights at every common
  rebalance. If two collapse to near-identical, the solver stalled below
  tolerance (known trap on tiny daily-return covariances) - FIX THE SCALING,
  do not silently accept it. Optimisers scale to percent internally; the
  backtest passes decimal mu/cov (see `ai/prompt_log.md` Entry 1).
- Every report number must trace to one of the CSVs under `results/`
  (`results/data/fund_returns.csv`, `results/data/fund_weights.csv`,
  `results/data/sector_sentiment_index.csv`,
  `results/tables/performance_metrics.csv`,
  `results/tables/fusion_comparison.csv`). Never build a figure/table from a
  hand-computed number.
- fund ids are `{family}_{method}` and methods contain underscores
  (`min_variance`, `max_sharpe`, `risk_parity`). Parse ids with
  `portfolios.parse_fund_id` (`split("_", 1)`), never `rsplit` - see
  `ai/prompt_log.md` Entry 2.
- Score headlines on the RAW text (no lowercasing/stripping - VADER needs caps
  and punctuation). Keep the two-pass, sign+magnitude agreement rule for the
  lexicon extension; never average a disagreement away
  (`ai/lexicon_extension_log.md`).

## Code layout

- `src/etl.py` - loading + integrity checks + combined calendar handling (Part A port).
- `src/features.py` - daily returns, wide panels, headline assembly (Part A port).
- `src/portfolios.py` - optimisers, walk-forward OOS backtest, metrics, turnover.
- `src/sentiment.py` - VADER + finVADER-lite + sector sentiment index.
- `src/fusion.py` - sentiment tilt baseline (equity min-variance base).
- `src/plots.py` - all report figures, via the shared FT style `src/style.py`.
- `scripts/run_part_b.py` - end-to-end orchestration; run from the project root.
- `streamlit_app.py` - the Station 4 app entrypoint (reads `results/` only; no
  `src.*` or nltk imports - the app must never run a backtest/optimiser/sentiment
  model).
- `app/data.py` - the app's pure data layer (no streamlit import): loads the
  `results/` CSVs (incl. `fund_fees.csv`),
  derives the Equity/Crypto/Multi-Asset universe grouping from the data (never
  hardcode the fund list), and does the blend/drawdown/gauge/fee/portfolio-metrics
  math. `app/formatting.py` - shared `format_date` / `metric_label` helpers.
- `tests/test_smoke.py` - sanity checks (no-look-ahead, weight sums, no negatives,
  methods differ, CSV traceability).
- `tests/test_app.py` / `tests/test_app_data.py` - AppTest smoke tests for the
  five app tabs (incl. portfolio save/list/delete) + unit tests for the data layer.
- `ai/` - prompt log (see `ai/prompt_log.md`), template (`ai/prompt_log_template.md`) and `ai/lexicon_extension_log.md`.

## Workflow

- Reproduce everything with: `python scripts/run_part_b.py`
- Check with: `python -m pytest -q tests/`
- Do not run `scripts/check_handin.py` for real until the student signs off on
  the final hand-in pass (prompt_01-06 implemented and tested; the app's five
  sections plus the fully-interactive variant funds are in).
- Log problems in `ai/` as they happen (graded, 20% AI Workflow & Transparency):
  solver stalls, look-ahead bugs, judgement calls. Not retroactive summaries.
- The user (student) is the final reviewer of every output. Present results
  with the 22 Sharpe ratios (12 core + 10 grouping), the vol-target comparison,
  surprises, and deviations from the prompt.
