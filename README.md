# FinTech Project - Part B

Part B: funds, sentiment, and the app (DFF Stations 3-4). Station 3 (this
build) produces the 22 out-of-sample funds (12 core + 10 grouping funds), the
sentiment index, the fusion baseline, and a volatility-targeting overlay.
Station 4 (the Streamlit app) is built and polished (see the prompt_04,
prompt_05 and prompt_06 sections below).

## Live App

- GitHub repository: https://github.com/rayt737/z5710071_projectB
- Live Streamlit app: https://z5710071projectb.streamlit.app/

## How to run

    python -m pip install -r requirements.txt -r requirements-dev.txt   # dev adds nltk (VADER)
    python scripts/run_part_b.py            # reproduces all Station 3 outputs into results/
    python tests/test_smoke.py              # sanity checks (also runnable via pytest)
    streamlit run streamlit_app.py          # Station 4 app - reads results/ only

Load raw data through `src/data_access.py` (see `context/DATA_GUIDE.md`); never
commit raw data. The deployed app, by contrast, reads your precomputed
artifacts from `results/` - those ARE committed.

## Station 3 design decisions (stated, per ai/prompts/prompt_01.md)

- **Rebalance**: monthly, on the first trading day of each month. First live
  date is derived from the real data (first rebalance after the initial window):
  2021-01-04 for equity and combined, 2021-01-01 for crypto. Not hardcoded.
- **Window**: expanding; initial estimation window = first year of that
  universe's calendar (252 trading days for equity/combined, 365 days for
  crypto).
- **No look-ahead**: at rebalance date *t*, mu/cov are estimated from rows
  strictly before *t*; the sentiment signal is lagged one trading day. Explicit
  assertions (`assert_no_lookahead`) enforce both - not careful indexing.
- **Long-only, fully invested**: every fund's weights are `>= 0` and sum to 1
  at every rebalance (clip + renormalise after each solve; asserted in tests).
- **Risk-free rate = 0** for Sharpe ratios.
- **Annualisation**: equity and combined use sqrt(252); crypto uses sqrt(365).
  Returns are computed within each panel; combined = crypto returns left-merged
  onto the equity trading calendar (weekend-only crypto moves dropped).
- **Optimiser sanity**: all four methods must differ pairwise at every common
  rebalance; a collapse raises instead of being silently accepted (this caught
  a real double-scaling bug - see `ai/prompt_log.md` Entry 1).
- **No-news stock-days** in the sentiment index: carried forward (ffill);
  stock-days before a stock's first headline are neutral 0 (no information
  yet). Carry-forward chosen because absence of a headline does not mean
  neutral sentiment, and dropping them would hollow out the index on quiet
  days.
- **Sector index**: equal-weight the stocks within each sector; the saved
  `sentiment` column is lagged one equity trading day.
- **Fusion**: rolling z-score over the last 60 trading days, `w_tilt_i =
  w_base_i * (1 + lambda*z_i)`, clip negatives, renormalise. lambda = +1
  (momentum) and -1 (contrarian), deliberately untuned, before transaction
  costs. Applied to the equity min-variance fund only (sentiment does not touch
  crypto).
- **finVADER-lite** is a novel, small finance-lexicon extension to plain VADER
  (35 terms, grounded in the Loughran-McDonald Master Dictionary, two-pass
  rated). It is NOT the pre-built finVADER PyPI package - see
  `ai/lexicon_extension_log.md`.

## Station 3 extension (prompt_02) - 10 grouping funds & vol-targeting

- **New groupings use equal-weight and risk parity ONLY.** No market-cap data
  exists in this dataset, so the two optimisers that need a return/risk estimate
  (min-variance, max-Sharpe) would be built on guesswork; only the two methods
  needing no estimate are "fair". Same walk-forward methodology as the core 12:
  expanding window, monthly rebalance, no look-ahead, long-only fully invested,
  correct annualisation per universe.
- **Equity sector clusters** (from the `sector` column, never hardcoded ticker
  lists): Defensive = {Healthcare, Utilities, Consumer}, Cyclical =
  {Financials, Industrials, Materials, RealEstate}, Growth/Sensitive = {Tech,
  Comm, Energy}. Annualise sqrt(252). Stated judgement call: the dataset merges
  Consumer Staples and Discretionary into one `Consumer` sector, placed in
  Defensive.
- **Crypto themes** (explicit ticker lists): Payment Infrastructure = {XRP,
  LTC, BCH, XLM}, Web3 Infrastructure = {ETH, ADA, ETC, TRX, EOS}. Annualise
  sqrt(365). BTC-USD excluded from both (store of value, neither a payment rail
  nor a smart-contract layer). Stated judgement call: TRX-USD placed in Web3 -
  architecturally a smart-contract platform, despite its dominant stablecoin
  usage.
- **Fund ids** `{family}_{method}` with `family in {defensive, cyclical,
  growth_sensitive, payments, web3infra}` and method in {equal_weight,
  risk_parity}, appended to the SAME CSVs as the core 12 (no parallel files).
  Because `growth_sensitive` itself contains an underscore,
  `portfolios.parse_fund_id` infers the method by known-suffix matching rather
  than splitting - see `ai/prompt_log.md` Entry 6.
- **Volatility-targeting overlay** (Moreira & Muir, 2017; `src/vol_target.py`):
  target vol = annualised realised vol over the fund's **initial estimation
  window only** (252 equity/combined, 365 crypto) - the same pre-live window
  that set the fund's first out-of-sample weights, fixed once before live
  trading and never recomputed, so the target carries no out-of-sample
  information (no look-ahead; see `ai/prompt_log.md` Entry 7). The overlay runs
  on the fund's full history (pre-live implied returns from the first-rebalance
  weights + OOS returns) so the trailing window is causal from day 1 of live
  trading. Trailing realised vol = 60-trading-day rolling std of daily returns
  (window ends strictly before *t*, explicit `assert_no_lookahead`); k_t =
  target/realised_(t-1) clipped to [0.5, 1.5]; scaled return = k_t * r_t.
  Applied to Combined Maximum-Sharpe (worst core drawdown, -52.7%) and, for
  comparison, Crypto Maximum-Sharpe.

## Station 3 extension (prompt_03) - investor-facing display names

- **Fund ids stay technical everywhere.** The `fund` columns of
  `fund_returns.csv` / `fund_weights.csv` / `performance_metrics.csv`,
  `portfolios.parse_fund_id`, prompt logs and tests are unchanged. Display
  names are a presentation-only lookup.
- **`src/branding.py`** holds the mapping: `DISPLAY_NAMES` (the 22 base funds,
  e.g. `equity_equal_weight` -> "Invesper US Equity Index Fund"),
  `FUSION_DISPLAY_NAMES` (momentum/contrarian -> "(Momentum)" / "(Contrarian)")
  and `VOL_TARGET_DISPLAY_NAMES` (combined/crypto max-Sharpe ->
  "(Managed Vol)"). `fund_display_name(fund_id)` resolves base ids and every
  CSV variant row (`{base}_base`, `{base}_{variant}`, `{label}_vol_targeted`).
- **`results/data/fund_display_names.csv`** (written by `run_part_b.py`, 29
  rows: 22 base + 7 variant ids) is what the Station 4 app reads to label any
  fund id.
- **Every human-readable render point** in `src/plots.py` uses display names:
  metrics-table rows, growth-of-$1 legends/titles, Sharpe barplot tick labels,
  grouping legends, fusion legend, vol-target titles/legends, drawdown and
  weights-over-time titles. Technical fund ids still appear in captions for
  CSV traceability. Figure sizes/label wrapping tuned so long names render
  without truncation or tick-label overlap.

## Station 4 app (prompt_04/05/06) - the five user actions

- **`streamlit_app.py`** (repo root, replaces the stub) is the entrypoint. It
  reads precomputed `results/` only - no backtest, optimiser, VADER/nltk, or
  sentiment re-scoring anywhere in the app or anything it imports (grep-checked
  in the tests). Data loads are cached with `st.cache_data`.
- **`app/data.py`** is the pure data layer (no streamlit import): it loads the
  CSVs under `results/`, derives the universe grouping from the data, and
  implements the blend / drawdown / gauge / portfolio-metrics math so it is
  unit-testable without a browser. **`app/formatting.py`** holds the shared
  date (`01 January 2021`) and metric-label helpers (prompt_06).
- **Five tabs** (the brief's four user actions plus the prompt_06 Portfolio
  tab):
  1. **Compare** - per-universe metrics table plus a horizontal Sharpe bar
     chart (switch universe with a radio); table headers and chart use
     humanised metric labels.
  2. **Fund fact sheet** - pick a fund; growth-of-$1, drawdown, the four
     headline metrics, current-holdings bar chart, display-name title. All 26
     funds - the 22 base funds plus the 4 extension variants - render real
     charts (prompt_05; their daily series are appended to `fund_returns.csv`).
     Vol-targeted variants show their base fund's holdings with the caption
     "Volatility targeting scales overall exposure, not individual holdings".
  3. **Sentiment** - sector index lines (multi-select) and a market-wide 0-100
      fear/greed gauge (0 = Fear - 100 = Greed). The app never loads the
      146,836-row per-headline table or the precomputed lexicon comparison; the
      lexicon summary stays in `results/` for the report only.
  4. **Allocation** - build a portfolio from any of the 26 funds (22 base + 4
     variants) across universes; per-fund weights normalised to 100%. Each
     slider shows its fund's annual fee; the blended fee (weighted average,
     charged daily on AUM) drives the gross vs net growth lines, with the
     one-two-line zero-commission pricing line below. The real 26-entry fee
     schedule is committed as `results/data/fund_fees.csv` (prompt_06).
  5. **Portfolio** - "Submit portfolio" saves a copy of the current allocation
     (name auto-uniquified) as a session-only portfolio: donut of weights,
     gross vs net growth, four headline metrics annualised on the portfolio's
     own observed trading calendar, and delete (prompt_06).
- **Universe grouping is data-driven, not hardcoded**: family -> universe from
  the `family` column of `performance_metrics.csv` (Equity 12 / Crypto 9 /
  Multi-Asset 5); fusion variants are always Equity; vol-targeted variants
  inherit their base fund's universe. Only the family/method sort order is a
  constant. The `{base}_base` duplicate rows in the comparison CSVs are
  excluded. A test pins the exact membership.
- **Every fund label is a display name** from
  `results/data/fund_display_names.csv` (never a raw id; no `src.branding`
  import in the app - the CSV is the interface, see prompt_03).
- Details behind the visible choices (blend calendar alignment, fee mechanics,
  gauge rescaling) are in `ai/prompt_log.md` Entry 9; the variant series
  persistence and vol-target holdings fallback are in Entry 10; the design/
  polish pass (dates, labels, horizontal Sharpe, native lexicon chart, fee
  schedule, Portfolio tab) and the empirical per-portfolio annualisation are
  in Entry 11.

## Station 4 extension (prompt_05) - the 4 variants are fully interactive

- **`fund_returns.csv` now carries the 4 extension-variant daily series** (26
  funds total): the 2 fusion tilts (equity calendar) and the 2 vol-targeted
  overlays (their base fund's OOS calendar), appended in
  `save_funds_and_metrics`. No app-side special cases remain - growth-of-$1 and
  drawdown work for them automatically because they are driven by that CSV.
- **Fusion variants have their own weight rows** in `fund_weights.csv`: the
  tilt is recomputed at the base fund's monthly rebalance dates, so the same
  schema applies and "current holdings" works unchanged.
- **Vol-targeted variants store no weight rows** - the overlay is a portfolio-
  level scalar (`k_t`), so their holdings are the base fund's. The fact sheet
  falls back via `app.data.base_fund_of` with the explanatory caption.
- **Allocation builder** includes all 26 funds; **gauge** caption states the
  reading is unlagged and display-only while fund construction uses the lagged
  signal shown in the sector chart.

## Station 4 design pass (prompt_06) - dates, labels, fees, Portfolio tab

- **Dates** are long-form (`01 January 2021`) at every point-in-time text site
  via the single `app/formatting.py` helper; chart axis ticks are untouched.
- **Metric labels** ("Sharpe Ratio", "Max Drawdown", ...) come from one lookup
  dict; the Compare Sharpe chart is horizontal and sorted.
- **The Portfolio tab annualises on the portfolio's own observed trading
  calendar** (`observed days / years spanned`, derived from the blend's date
  union), never a flat 252 - a crypto-inclusive blend trades ~365 days/year.
  The caption states the factor. Published fund metrics keep sqrt(252)/
  sqrt(365) per family (see `ai/prompt_log.md` Entry 11).

## Outputs (every report number traces to these files)

| File | Contents |
|------|----------|
| `results/data/fund_returns.csv` | LONG format: one row per (date, fund) with `return` = that fund's daily simple return over its out-of-sample period. 26 fund ids: the 22 base funds + the 4 extension-variant series (2 fusion tilts + 2 vol-targeted, appended since prompt_05). |
| `results/data/fund_weights.csv` | LONG format: one row per (fund, rebalance_date, ticker) with `weight` = the target weight held at that rebalance. 24 fund ids: the 22 base funds + the 2 fusion tilt series (same monthly rebalance dates). Vol-targeted variants intentionally have NO rows - their holdings are the base fund's (see prompt_05 section). |
| `results/data/headline_sentiment.csv` | Per-headline scores: date, ticker, sector, title, url, publisher, `plain_vader`, `finvader_lite` (146,836 rows). |
| `results/data/fund_display_names.csv` | `fund_id` -> investor-facing `display_name` lookup for the app (29 rows; see prompt_03 section above). |
| `results/data/fund_fees.csv` | `fund_id` -> `fee_annual` for all 26 app-eligible funds, written by the pipeline from `src/branding.FEE_SCHEDULE` (the app never imports `src.*`; prompt_06). |
| `results/data/sentiment_lexicon_comparison_summary.csv` | Small precomputed summary of the VADER-vs-finVADER comparison (monthly_mean 96 rows, 60-bin histogram per lexicon 120 rows, neutral-headline share 1 row). Report-only - the app does not read it (prompt_06; see Entry 12 in `ai/prompt_log.md`). |
| `results/data/sector_sentiment_index.csv` | date, sector, `sentiment` (LAGGED 1 trading day - the tradable signal), `sentiment_aligned` (display only), n_stocks. |
| `results/tables/performance_metrics.csv` | 22 funds x {annualised return, vol, Sharpe, max drawdown, total return, turnover, first/last live date}. rf = 0. |
| `results/tables/fusion_comparison.csv` | equity min-variance base vs momentum (lambda +1) vs contrarian (lambda -1), before costs. |
| `results/tables/vol_target_comparison.csv` | base vs vol-targeted performance for Combined and Crypto Maximum-Sharpe (same metric shape as fusion_comparison.csv, `target_vol` instead of `lambda`). |

`results/figures/` holds the self-contained Station 3 exhibits (metrics table,
growth-of-$1 per universe, combined max-Sharpe drawdown, weights-over-time by
sector, 22-fund Sharpe barplot, VADER vs finVADER-lite comparison, sector
sentiment over time, fusion growth comparison, sector-cluster and crypto-theme
growth, and the vol-target growth + scaling-factor figures). Every growth-style
figure carries colour-matched `$X.XX` end-of-line value labels (ported from
Part A) and the sample period. All figures share the Part A FT-style theme from
`src/style.py`.

## What is here

- `streamlit_app.py`    the app entrypoint (repo root, Station 4 - first pass; reads results/ only)
- `app/`                the app's pure data layer (`app/data.py`); no streamlit/model imports
- `.streamlit/`         app config
- `PROJECT_BRIEF.md`    the full assignment brief for your course (read this first)
- `src/`                your code (data_access provided; etl/features ported from Part A; portfolios/sentiment/fusion/vol_target/branding/plots are yours)
- `scripts/`            runnable scripts that reproduce your results
- `results/`            your outputs: figures in results/figures/, tables in results/tables/, app data artifacts in results/data/
- `context/`            provided data guide and project context (do not edit)
- `report/`             your report - see report/OUTLINE.md (author in Word, submit report.pdf)
- `ai/`                 your prompt logs and AI notes (graded)
- `requirements-dev.txt` build/repro-only deps (nltk); keep them out of the deployed app
- `AGENTS.md` / `CLAUDE.md`   your agent instruction files (replaced the stubs)

## Deploy + hand in

This folder is its own GitHub repo, independent of fins-agent. See
PROJECT_BRIEF.md Appendix D and docs/STUDENT_DEPLOY.md (in this folder). In short:

    python scripts/check_handin.py        # prompts 01-05 done - run only with the student's hand-in sign-off

Then commit the precomputed artifacts under `results/`, push to a private
GitHub repo, and connect it on share.streamlit.io (entrypoint
`streamlit_app.py`). Make the repo public at hand-in, submit the live URL +
repo link, and zip the whole folder to Moodle.
