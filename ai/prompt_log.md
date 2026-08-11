# Prompt Log - Part B: Funds, Sentiment & Fusion (Station 3)

## Entry 1: Optimiser solver stall & double-scaling bug

### What I wanted
Walk-forward out-of-sample backtest for 12 funds. Each rebalance estimates
mu/cov from the estimation window (expanding), then solves a long-only,
fully-invested portfolio (min-variance, max-Sharpe, risk parity) and holds it
for a month.

### Prompt(s)
"Build the four optimisers (equal-weight, min-variance, max-Sharpe, risk
parity) as functions taking (mu, cov) -> weights, plus a dispatcher, and run
them monthly in a walk-forward backtest across equity, crypto, and combined
universes."

### What the assistant produced
Optimisers written with scipy SLSQP. Two failures surfaced immediately:

1. SLSQP returned `Positive directional derivative for linesearch` — failure
   to converge — on many rebalances. Daily simple returns are tiny (order
   1e-2 to 1e-4), so the covariance matrix is orders of magnitude smaller than
   the solver's default function/variable tolerances, and SLSQP stalls below
   tolerance.
2. Worse, the combined-universe min-variance fund's weights collapsed to
   EXACTLY equal-weight (1/60 each). The backtest had been scaling returns by
   100 before computing mu/cov (`hist = returns * 100`), while the optimiser
   scaled the covariance by 10000 again. The result: min-variance objective
   `w'Sigma w` was multiplied by ~1e8 relative to the constraint scale, the
   solver found the equally-weighted start point "good enough", and stopped —
   silently producing the wrong fund. My own `backtest_all_methods` sanity
   check (methods must differ pairwise) caught it: min-variance == equal-weight
   within the tolerance, which raised the assertion instead of passing silently.

### What was wrong or risky
- Relying on one solver with default tolerances on badly scaled inputs is
  fragile and fails silently — the collapse bug was a "wrong answer, no error"
  outcome, the worst kind.
- Double-scaling (returns scaled in the backtest AND covariance scaled in the
  optimiser) is exactly the kind of thing that produces it.

### What I changed and why
- The backtest now passes **decimal** mu/cov to the optimisers; all percent
  scaling happens inside the optimiser functions only, once (`cov * 10000`,
  `mu * 100`), so there is a single scaling point.
- Added analytic gradients for min-variance and max-Sharpe (cheap and exact)
  and a `trust-constr` fallback when SLSQP reports failure.
- Warm-started each rebalance from the previous month's weights (feasible
  point) to help convergence.
- After every solve, clip tiny negatives and renormalise so `sum(w) = 1`
  exactly holds.
- Kept the pairwise-method-difference assertion across ALL rebalances as a
  permanent guard: if two methods ever collapse again, the pipeline raises
  rather than silently accepting it.
- Verified: all four methods now produce genuinely different weights at every
  common rebalance date in all three universes (the assertion passes).

### Files
`src/portfolios.py` — `_solve_long_only`, `min_variance`, `max_sharpe`,
`risk_parity`, `assert_methods_differ`, `oos_backtest`.

---

## Entry 2: Fund-id parsing bug (`rsplit` vs `split`)

### What I wanted
A canonical fund id per (universe, method) so the metrics table, CSVs, figures,
and app all reference the same 12 funds: `{family}_{method}`, e.g.
`equity_min_variance`. I needed a helper to recover (family, method) from an id.

### Prompt(s)
"Write a function that splits a fund id like 'equity_min_variance' back into
(family, method) so we can look up annualisation factors per family."

### What the assistant produced
```python
family = fund.rsplit("_", 1)[0]   # WRONG
method = fund.rsplit("_", 1)[1]   # WRONG
```

### What was wrong or risky
`rsplit("_", 1)` splits on the LAST underscore. Three of the four method names
themselves contain underscores (`min_variance`, `max_sharpe`, `risk_parity`),
so `"equity_min_variance"` parsed as family = `"equity_min"`, method =
`"variance"`. That silently:
- looked up `ann_factors["equity_min"]` -> would KeyError at metrics time,
- and would have mislabelled every metric/figure row built from it.

The family is the FIRST token; only the method can contain underscores. The
bug hid because the backtest itself never parses ids — it only constructs them.

### What I changed and why
Replaced with `split("_", 1)` and added `parse_fund_id()` in
`src/portfolios.py`:

```python
def parse_fund_id(fund):
    family, method = fund.split("_", 1)
    if family not in FAMILIES or method not in METHODS:
        raise ValueError(f"unrecognised fund id '{fund}'")
    return family, method
```

The validation against the allowed families/methods means a bad parse raises
immediately instead of propagating wrong labels. Both the metrics table builder
and the plotting module now use it, and `tests/test_smoke.py::test_parse_fund_id`
covers `min_variance`/`risk_parity`/`max_sharpe` cases plus a bad id.

### Files
`src/portfolios.py` (`parse_fund_id`), `src/plots.py` (`fig_metrics_table`,
`fig_sharpe_barplot`), `tests/test_smoke.py`.

---

## Entry 3: Weights index name & figure-period bugs

### What I wanted
`scripts/run_part_b.py` to save `results/data/fund_weights.csv` (long:
fund, rebalance_date, ticker, weight) and produce self-contained figures whose
captions state the sample period.

### Prompt(s)
"Save the backtest weights as a long CSV and put the sample period in each
figure caption."

### What the assistant produced / what broke
Two runtime errors, both caught in the first full-pipeline run:

1. `KeyError: id_vars ['date'] not present` when melting weights.
   `weights = pd.DataFrame(weights_rows)` inherits its index name from the
   Series name each row was created with — a raw `Timestamp` (the rebalance
   date), not the string `"date"`. So `reset_index()` produced a column named
   by that Timestamp and `.melt(id_vars="date")` failed.
2. `AttributeError: 'numpy.int64' object has no attribute 'strftime'` in the
   figure caption helper `_period`. I had written
   `pd.Series(...).sort_values().index.min()` — but `.index` of a freshly made
   Series is a `RangeIndex`, so `.index.min()` returns the position `0`, not a
   date.

### What was wrong or risky
- A missing index-name caused a confusing KeyError in the orchestration.
- The period caption bug was a silent-wrong-value risk: without the error it
  could have printed "Jan 0 – 0" style nonsense in captions.

### What I changed and why
- `oos_backtest` now sets `weights.index.name = "date"` so every downstream
  consumer (melt, save, plotting) gets a stable column name.
- `_period` now takes the Series values, not the index:
  `pd.Timestamp(returns.min())` / `returns.max()`.

### Files
`src/portfolios.py` (`oos_backtest`), `src/plots.py` (`_period`).

---

## Entry 4: Lexicon candidate-count gap (55 vs 37)

### What I wanted
Resolve a discrepancy between the reported count of candidate finance terms and
the committed lexicon. The Station-3 report-back mentioned `build_lexicon_candidates`
identifying candidate terms, but a reviewer counted that `finvader_lite_extension.csv`
only contains 37 terms — an apparent gap. The instruction: check the actual screen
output against the CSV and the log, explain every missing candidate (filtered
before rating with an explicit criterion, or a real bug to fix), rewrite
`ai/lexicon_extension_log.md` so it accounts for all candidates with no silent
gap, and — only if the final term set changes — re-run sentiment scoring and
everything downstream.

### Prompt(s)
"Your own report-back on Station 3 said build_lexicon_candidates identified 55
candidate finance terms, but the committed CSV only accounts for 37... Work out
exactly why 18 are missing — either filtered before rating (with an explicit
criterion) or dropped during rating (a bug). Rewrite the log to account for all
candidates. If it changes the final 37 terms, re-run sentiment scoring and
everything downstream. If not, say so explicitly and confirm no re-run was
needed."

### What the assistant produced / what I found
Investigation (all numbers recomputed, not guessed):

- **The "55" was a stale development count.** An early screen run over a
  partial corpus (~60k headlines) returned 55 candidates. On the full 146,836
  headline corpus the screen yields **80** candidates, and the committed log
  already said 80. The 55 was never in the log.
- **The CSV's 37 terms do NOT all come from the screen.** Only **21** of the 37
  (19 kept + 2 flagged) appear in the screen output. The other **16** were added
  by a manual coverage review and are not reproducible from the screen call:
  - 5 inflections of rated families below the >= 40-headline cutoff
    (rebounded, outperformed, surpassed, declined, downgrade);
  - 7 terms that qualify but rank past the top-80 display bound
    (risky, layoffs, uncertain, overvalued, bankruptcy, rebounding, downgraded);
  - 4 terms with no LM flag at all, accepted by inspection
    (upgrade, upgraded, upgrades, tailwinds).
- **59 of the 80 screen candidates are not in the CSV** — all deliberately
  filtered before rating, none dropped during rating:
  - 14 are already in VADER's default lexicon (cut, loss, risk, ignore,
    shortage, lawsuit, warns, challenge, lost, loses, lose, challenges,
    dispute, turmoil) — VADER already scores them, no gap to fill;
  - 45 excluded by category: 10 modal/hedging, 11 litigious-process,
    24 context/judgement.
- **The log had a traceability weakness, not a rating bug.** Section 2's family
  labels miscounted (11/14 vs the 13/17 words actually listed) and implied all
  37 shortlisted terms came from the screen; Section 4's "43 of the 80 not
  taken forward" was arithmetic filler (80 − 37) that did not match the real
  59-term exclusion. The `top_n=80` bound was also presented as the complete
  candidate universe when the true qualifying pool is 124 terms.

### What was wrong or risky
- A reviewer (or the student) could not reproduce the CSV from the committed
  screen call: 16 CSV terms had no code path, and 59 screen candidates had no
  recorded reason. That looks like silently dropped terms even though nothing
  was actually dropped — a reproducibility and audit-trail gap in a graded
  "AI Workflow & Transparency" deliverable.
- The screen's `top_n=80` display bound silently hid 7 genuinely qualifying
  terms that were later admitted by coverage — the count could never be
  reconciled from the log alone.

### What I changed and why
- **No scoring change — the final 37 terms are untouched.** The gap was in
  accounting/traceability, not in which terms ended up in the lexicon. Every one
  of the 37 was two-pass rated (both pass columns present in the CSV) and 35
  were kept; the fix changes documentation, not results.
- Added `scripts/audit_lexicon_traceability.py`, which regenerates
  `results/tables/lexicon_candidate_ledger.csv` (96 rows: 80 screen candidates
  + 16 coverage additions) with a **disposition for every candidate and an
  explicit reason for every extension term**. It asserts airtightness (non-zero
  exit if any candidate has no disposition or any term is unexplained).
- Added `top_n=None` support to `build_lexicon_candidates` so the audit can use
  the **full 124-term qualifying pool** instead of the truncated top-80 screen.
- Rewrote `ai/lexicon_extension_log.md` to account for all 124 pool terms and
  all 37 rated terms: 21 rated from the screen, 16 by documented manual
  coverage (each with its exact reason), 59 screen candidates excluded with
  explicit criteria and enumerated lists.
- Added `tests/test_smoke.py::test_lexicon_ledger_complete` so CI re-verifies
  the ledger (every extension term explained; every screen candidate has a
  disposition).

### Did the final results change?
**No.** The fix touches no lexicon values and no pipeline inputs, so
`results/data/headline_sentiment.csv`, the sector sentiment index, fusion
outputs, and all 12 Sharpe ratios are unchanged. **No downstream re-run was
needed.** The only re-generated file is the new audit ledger.

### Files
- `scripts/audit_lexicon_traceability.py` (new)
- `results/tables/lexicon_candidate_ledger.csv` (new)
- `src/sentiment.py` (`build_lexicon_candidates`: `top_n=None` support only)
- `ai/lexicon_extension_log.md` (rewritten accounting)
- `tests/test_smoke.py` (new ledger-completeness test)

---

## Entry 5: Figure-caption epoch bug ("Jan 1970") & generic footer line

### What I wanted
Every Station-3 figure caption must state its own real sample period and a
footer that actually describes that figure. Two Station-3 caption bugs were
flagged: `drawdown_combined_max_sharpe.png` read "Out-of-sample period Jan 1970
- Jan 1970", and several non-return figures (`sector_sentiment_index.png`,
`sentiment_lexicon_comparison.png`,
`portfolio_weights_combined_min_variance.png`) carried the generic line
"Returns are simple daily returns.", which is meaningless for weights/sentiment
exhibits.

### Prompt(s)
"Fix both caption bugs; verify every figure's caption, not just the obvious
one; log as a new prompt-log entry."

### What the assistant produced / what I found (root cause)
Two independent bugs in `src/plots.py`:

1. **The "Jan 1970" period.** `_period(returns)` did
   `pd.Timestamp(returns.min())`. For the drawdown figure the argument is a
   Series of *daily return floats*, so the minimum return (~ -0.09) was read as
   **nanoseconds since the Unix epoch** and formatted as January 1970. Every
   other figure passed actual datetime indexes to `_period` (or computed the
   period inline from dates), which is exactly why only the drawdown figure
   broke — the helper's contract was "pass me a date-like Series" but nothing
   enforced it, and one caller silently passed returns values.
2. **The generic footer.** `_caption(source, period)` hardcoded
   "Out-of-sample period {period}. Returns are simple daily returns." on every
   figure, so the weights, lexicon-comparison and sector-index figures all
   claimed to show daily returns.

### What was wrong or risky
- The epoch bug is the worst class of plotting bug: a wrong-but-valid-looking
  date that a reviewer or student could carry into the report. It also showed
  the helper was mis-trustable (float values accepted without complaint).
- The copy-pasted default caption misdescribed three distinct exhibits and
  would mislead anyone reading the figures in isolation — figures are meant to
  be self-contained in this project.

### What I changed and why
- `_period(dates)` now takes an explicit date collection (a Series/Index of
  datetimes) and derives the range from the dates themselves, never from a
  returns value or a positional index. The drawdown caller passes
  `_period(returns.index)`.
- `_caption(source, period, content)` now requires a figure-specific content
  line; every figure passes an accurate one:
  - weights → "Weights are target allocations at each monthly rebalance.";
  - lexicon comparison → "Scores are per-headline VADER compound sentiment
    (plain vs finVADER-lite).";
  - sector index → "Index is the lagged sector-level sentiment signal.";
  - drawdown → "Drawdown is the cumulative fall from the running peak; returns
    are simple daily returns.";
  - growth/fusion → describe simple daily returns compounded from $1 (accurate
    for those figures).
- Added `tests/test_smoke.py::test_figure_captions_real_periods`: runs every
  `fig_*` function with synthetic data (capturing captions via a patched
  `save_fig`) and asserts no "1970", no stale default text, and that every
  caption's years are >= 2020.
- Regenerated everything with `python scripts/run_part_b.py` and verified the
  **rendered** PNG text by OCR of the actual saved images, not by reading the
  code: all 10 figures show real periods (Jan 2020/2021 - Dec 2023; metrics
  table and Sharpe barplot show full dates 2021-01-01 to 2023-12-31) and each
  footer describes its own figure.

### Files
- `src/plots.py` (`_period`, `_caption`, all eight `fig_*` callers)
- `tests/test_smoke.py` (new figure-caption regression test)
- `results/figures/*` (all regenerated)
- `ai/AI_NOTES.md` (test count 17 → 18)

---

## Entry 6: prompt_02 - 10 grouping funds, growth-of-$1 end labels, vol-targeting

### What I wanted
Implement `ai/prompts/prompt_02.md` in full:
1. Five new fund groupings (10 funds, equal-weight + risk parity only — no
   market-cap data exists, so only the two methods needing no return/risk
   estimate are "fair"): equity sector clusters Defensive / Cyclical /
   Growth/Sensitive (from the `sector` column, never hardcoded tickers) and
   crypto themes Payment Infrastructure / Web3 Infrastructure (explicit ticker
   lists, BTC-USD excluded).
2. Port Part A's growth-of-$1 **end-of-line value labels** into Part B, applied
   to every growth figure.
3. A Moreira & Muir (2017) volatility-targeting overlay on the Combined
   Maximum-Sharpe fund (worst drawdown, −52.7%).

### Prompt(s)
`ai/prompts/prompt_02.md` (new groupings with stated judgement calls; port Part A's
`_plot_growth_of_1` end-labelling; build the vol-target overlay with no
look-ahead; 10 new Sharpe ratios + vol comparison numbers; extend tests, log,
READMEs).

### What the assistant produced / what broke
- The grouping funds, vol-target module (`src/vol_target.py`), and the shared
  `label_end_values` helper in `src/style.py` were written and the pipeline ran
  end-to-end on the first full pass.
- **Bug caught immediately by the caption test (not by the pipeline):**
  `parse_fund_id` split ids with `split("_", 1)`, which worked while every
  family id was underscore-free — but the new family id `growth_sensitive`
  contains an underscore, so `"growth_sensitive_equal_weight".split("_", 1)`
  yields `("growth", "sensitive_equal_weight")` and parsing raised
  `ValueError: unrecognised fund id`. The same wrong split existed in
  `run_part_b.py` (grouping subset in the summary) and in
  `build_vol_target_comparison`.
- A second, silent-bug risk: two `.str.split("_", 1)` calls (in
  `fig_growth_groupings` and `print_summary`) used the pandas idiom
  `.str.split(pat, n)` positionally, which raises `TypeError` at runtime in
  this pandas version — caught on the first pipeline run, not by tests.

### What was wrong or risky
- The Entry-2 fix (`split("_", 1)`, never `rsplit`) was written when only
  **methods** contained underscores. prompt_02 added an underscore-bearing
  **family** id, silently breaking the same invariant. Any hardcoded
  `split("_", 1)` in the codebase is now a latent bug.
- A family id like `growth_sensitive` would also have silently corrupted the
  summary subset and vol-target family lookup (first token = "growth") — wrong
  numbers that look right.

### What I changed and why
- **Rewrote `parse_fund_id` to be family-agnostic**: infer the method as the
  known `METHODS` suffix (`fund.endswith(f"_{method}")`) and take the leading
  slice as the family, validating both. This supersedes the Entry-2
  `split("_", 1)` guidance: with `growth_sensitive_*` ids, neither split
  direction is safe, so the method must be matched from a known set. Docstrings
  updated to explain why a plain split no longer works.
- Replaced every other `split("_", 1)` / positional `.str.split` on fund ids
  with `pf.parse_fund_id(...)` (summary subset in `run_part_b.py`,
  `fig_growth_groupings` family list, `build_vol_target_comparison`).
- Extended `tests/test_smoke.py`: `test_output_csvs_traceable` now expects the
  full 22-fund id set and the 4-row `vol_target_comparison.csv`; new
  `test_group_funds_valid`, `test_group_backtests_methods_differ`,
  `test_group_universe_tickers_derive_from_data` (sector-derived clusters
  partition the universe; BTC-USD excluded from themes) and
  `test_vol_target_scaling_sane` (k in [0.5, 1.5], warm-up k = 1.0, no
  look-ahead, scaled = k * base); the caption test now exercises
  `fig_growth_groupings`, `fig_vol_target_growth`, `fig_vol_target_scaling`.

### Judgement calls (prompt_02)
- **`Consumer` placed in Defensive** (Utilities + Healthcare + Consumer): the
  dataset merges Staples and Discretionary into one sector, so the judgement
  call is stated in the prompt log and README, not silently assumed.
- **`TRX-USD` placed in Web3 Infrastructure** (ETH/ADA/ETC/TRX/EOS): Tron is
  architecturally a smart-contract platform (Web3), even though its dominant
  usage is stablecoin/payment settlement; BTC-USD (store of value, neither a
  payment rail nor a smart-contract layer) is excluded from both themes.
- **Vol-target design**: target vol = the base fund's OWN full-sample realised
  annualised vol; 60-trading-day trailing window (ends strictly before t);
  k_t clipped to [0.5, 1.5] (partial de-risking/scale-up, no real leverage);
  k = 1.0 during the 60-day warm-up.
- **Overlay applied to a second fund too**: crypto Maximum-Sharpe (worst
  crypto drawdown, −85.4%) as the optional second fund, for comparison.

### Result (recomputed from the CSVs under `results/`)
- **10 new grouping Sharpe ratios**: defensive 0.364 / 0.436; cyclical 0.674 /
  0.602; growth_sensitive 1.031 / 0.846; payments 0.597 / 0.588; web3infra
  0.894 / 0.913 (equal-weight / risk parity respectively).
- **Vol-targeting on Combined Max-Sharpe**: Sharpe 0.404 → 0.411; annualised
  return 14.05% → 14.52%; vol 34.83% → 35.34%; max drawdown −52.74% →
  −59.25%. On Crypto Max-Sharpe: 0.462 → 0.504; −85.42% → −87.85%. k_t within
  [0.535, 1.500] (combined) and [0.526, 1.500] (crypto).
- End labels verified on the rendered figures by OCR (`$X.XX` right-edge
  labels on growth_of_1_{equity,crypto,combined}.png, the two grouping figures
  and the two vol-target growth figures) and by a patched-call check in-process.
- All 22 tests pass; ruff clean on the changed files.

### Surprises
- **Vol-targeting barely moved volatility** (target = own full-sample vol makes
  the overlay a mean-reverting smoother around ~1, not a permanent de-risker)
  and **worsened the max drawdown** (k > 1 scaled exposure up in the calm
  regime before the crash). Both are honest consequences of the design; they
  are reported rather than hidden.

### Files
- `src/portfolios.py` (`GROUP_METHODS`, 5 new families, `SECTOR_CLUSTERS`,
  `CRYPTO_THEMES`, `ANNUAL_FACTORS`, `INITIAL_WINDOWS`, `group_universe_tickers`,
  `is_group_family`, `backtest_all_methods(methods=...)`, rewritten
  `parse_fund_id`)
- `src/style.py` (new `label_end_values` helper, ported from Part A)
- `src/vol_target.py` (new)
- `src/plots.py` (`fig_growth_of_1`, `fig_fusion_growth` end-labelled; new
  `fig_growth_groupings`, `fig_vol_target_growth`, `fig_vol_target_scaling`;
  Sharpe barplot colour map for 8 families)
- `scripts/run_part_b.py` (22-fund loop, vol-target wiring, summary)
- `tests/test_smoke.py` (5 updated/new tests; 18 → 22)
- `results/data/fund_returns.csv`, `results/data/fund_weights.csv`,
  `results/tables/performance_metrics.csv` (22 rows),
  `results/tables/vol_target_comparison.csv` (4 rows),
  `results/figures/*` (all regenerated, 16 PNGs)
- `README.md` (design decisions + output files)

---

## Entry 7: Vol-target target was look-ahead (full-sample vol) - fixed to initial-window vol

### What I wanted
Fix a look-ahead bias in the prompt_02 vol-targeting overlay and re-report
honestly. The target volatility was computed as the base fund's **full-sample**
realised annualised vol over 2021-2023 - the entire out-of-sample period. That
is not knowable on any live day: "full-sample vol" only exists once the whole
future, including the 2022 crash, has already happened. On a calm early-2021
day the future-inflated target sat above the realised trailing vol, so k_t > 1
and the overlay was leveraging the fund up right before the crash it
"knew" was coming - which is almost certainly why the overlay made the Combined
Max-Sharpe max drawdown WORSE (-52.7% -> -59.3%) instead of better.

### Prompt(s)
"target volatility ... computed as the base fund's full-sample realised
annualised volatility ... This is look-ahead bias ... change the target
volatility to be computed once, from the fund's initial estimation window only
... Report the new numbers honestly, whatever they are ... Add a new entry to
ai/prompt_log.md ... Update README.md."

### What the assistant produced / what I found
The diagnosis was correct and I confirmed the mechanism directly in the code:
`target_vol_of(returns, ann_factor)` called
`performance_metrics(returns, ann_factor)["annualised_volatility"]` over the
WHOLE OOS series, and `apply_overlay` and `build_vol_target_comparison` both
used it. The 60-day trailing-vol side was already causal (`shift(1)`, explicit
`assert_no_lookahead`); only the target leaked.

There was a second, structural issue behind the fix: the saved fund return
series starts at the first live date, so it contains NO estimation-window days.
To set a causal target from the initial window, the overlay needs the fund's
pre-live returns. I therefore built the fund's FULL history as: pre-live
implied returns (the fund's first-rebalance weights applied to the
estimation-window asset returns - the same data that set those weights, fully
known before day 1) concatenated with the OOS returns. The target is then the
annualised vol of the first `estimation_window` days of that full history, and
the trailing window is causal from the very first OOS day (the old design had
an artificial k = 1.0 warm-up during the first 60 OOS days for lack of data).

### What was wrong or risky
- The full-sample target is the exact look-ahead pattern the rest of the
  project is asserted against (funds, sentiment lag, fusion). It biased k_t
  UP before the 2022 crash, i.e. it produced a nicer-looking max drawdown
  comparison than any causal implementation could, by construction.
- The effect was subtle enough to look like a "surprise worth reporting" in
  Entry 6 rather than a bug; a reviewer had to flag it. A causal check on the
  target (it must be a pure function of the initial window) would have caught
  it at build time.

### What I changed and why
- `src/vol_target.py`:
  - `target_vol_of(fund_returns, estimation_window, ann_factor)` now computes
    annualised realised vol over the FIRST `estimation_window` days only and
    asserts causality: `assert_no_lookahead(window.index.max(),
    r.index[estimation_window])` - the last date used is strictly before the
    first date outside the window. It also raises if there is no out-of-sample
    day to anchor the check against.
  - `apply_overlay(full_returns, ann_factor, estimation_window, ...)` takes the
    estimation window explicitly, defaults the target to
    `target_vol_of(full_returns, estimation_window, ann_factor)`, and returns
    (scaled, k, target).
  - `build_vol_target_comparison(..., targets)` takes the causal targets
    instead of recomputing full-sample vol.
- `scripts/run_part_b.py`: new `build_full_history(panel, base_returns,
  weights)` constructs the pre-live segment (first-rebalance weights x
  estimation-window asset returns) + OOS returns; `build_vol_target` now
  receives the wide panels, runs the overlay on the full history, slices
  scaled/k back to the OOS period for the figures/table, and logs the target
  with its exact window dates.
- `tests/test_smoke.py`: `test_vol_target_scaling_sane` updated to the new
  signature; new `test_vol_target_target_is_initial_window_only` builds a
  calm-then-crashy series and asserts the target equals the initial-window vol
  (NOT the full-sample vol) and that corrupting any date outside the window
  cannot move the target.
- `src/plots.py`: vol-target growth caption now says the overlay scales toward
  the fund's initial-estimation-window volatility (fixed before live trading).
- README design-decision line updated to the corrected target.

### Result (recomputed from the regenerated CSVs; all figures/CSVs re-run)
Targets are now fixed from the 2020 estimation window only (well before the
first live date 2021-01-04):
- combined_max_sharpe: target vol 0.4835 (window 2020-01-03..2020-12-31),
  k_t in [0.741, 1.500]
- crypto_max_sharpe: target vol 0.7949 (window 2020-01-02..2020-12-31),
  k_t in [0.530, 1.500]

Corrected comparison (base vs vol-targeted):
- Combined Max-Sharpe: Sharpe 0.404 -> **0.307**; ann ret 14.05% -> 12.51%;
  vol 34.83% -> 40.72%; max DD -52.74% -> **-66.96%**.
- Crypto Max-Sharpe: Sharpe 0.462 -> **0.470**; ann ret 36.51% -> 37.08%;
  vol 78.99% -> 78.84%; max DD -85.42% -> **-88.05%**.

Verified: the regenerated `vol_target_comparison.csv` carries the causal
targets; the regenerated figures were OCR-checked (captions now say
initial-estimation-window vol; growth end labels $1.27 base vs $1.13
vol-targeted for Combined, matching the 27.0% vs 13.4% total returns in the
CSV); 23 tests pass; ruff clean on all changed files.

### Honest conclusion (not tuned)
With a causal target the overlay does NOT help: on Combined Max-Sharpe it makes
Sharpe and drawdown clearly worse, and on Crypto it is a near no-op with a
slightly worse drawdown. The mechanism: the 2020 estimation window includes the
COVID crash, so the target (48%) sits well above the 2021-2023 trailing vol -
k_t > 1 most of the time, i.e. the overlay systematically scales exposure UP
(leverage) rather than de-risking, and the 2022 crash then hurts more. The
brief explicitly says a careful extension that does not beat the baseline still
earns credit; nothing was tuned to look better.

### Files
- `src/vol_target.py` (causal target + full-history overlay API)
- `scripts/run_part_b.py` (`build_full_history`, `build_vol_target` wiring)
- `tests/test_smoke.py` (updated + new causal-target regression test; 22 -> 23)
- `src/plots.py` (vol-target growth caption)
- `results/tables/vol_target_comparison.csv` (regenerated, causal targets)
- `results/figures/growth_vol_target_*.png`, `results/figures/vol_target_scaling_*.png`
- `README.md` (vol-targeting design decision corrected)

---

## Entry 8: Investor-facing display names (Prompt 03)

### What I wanted
Give the 22 base funds plus the fusion/vol-target variants investor-facing
display names ("Invesper US Equity Index Fund", not `equity_equal_weight`)
used anywhere a person reads text: figure titles, legends, x-axis tick
labels, the metrics-table rows, and (later) the report and Station 4 app.
Fund ids stay exactly as they are everywhere they already matter.

### Prompt(s)
Prompt 03: create `src/branding.py` with `DISPLAY_NAMES` (22 funds) plus
`FUSION_DISPLAY_NAMES` and `VOL_TARGET_DISPLAY_NAMES`; do NOT rename any fund
id; write `results/data/fund_display_names.csv` from the dict as part of the
normal `run_part_b.py` run; apply the names at every render point in
`src/plots.py`; regenerate and spot-check figures for truncation/overlap;
run tests + ruff; log a new prompt_log entry; update README.md.

### What the assistant produced / what I found
The fusion variant keys in `src/fusion.py` / `fusion_comparison.csv` ARE
`momentum`/`contrarian` (the `fused_results` dict keys), and the vol-target
keys are `combined_max_sharpe`/`crypto_max_sharpe` (the `labels` list in
`build_vol_target`), so the prompt's dict keys matched the code exactly - no
renaming was needed. The comparison CSVs additionally identify their rows as
`{base}_base` / `{base}_{variant}` / `{label}_vol_targeted`, so
`fund_display_name()` resolves those full `fund`-column values too, and the
written CSV covers all 29 ids that appear anywhere (22 base + 3 fusion rows +
4 vol-target rows) so Station 4 can look up any fund id.

Rendering-time lookup only: the source CSVs' `fund` columns still carry the
technical ids (CSV traceability unchanged), and no `parse_fund_id` behaviour
was touched.

### What was wrong or risky
- Long names on a 22-bar Sharpe plot would collide or truncate if left at the
  old rotation/size. I verified with a layout check (perpendicular baseline
  separation between consecutive rotated tick labels vs the label block
  thickness) rather than eyeballing: at rotation 55°, fontsize 6.5, figsize
  14x6, tick spacing is 45 px and the perpendicular separation is 37 px vs a
  max block thickness of ~28 px - clean, ~9 px clearance. `save_fig` uses
  `bbox_inches='tight'`, so nothing is cropped.
- The metrics-table Fund column (~26% of table width) cannot hold a 50-char
  name on one line, so names are wrapped at word boundaries (2 lines max) and
  the figure was widened to 12x8 with colWidths re-balanced.
- The caption test built synthetic metrics from ALL families x ALL methods,
  producing ids like `defensive_min_variance` that do not exist in production
  and so are not in `DISPLAY_NAMES`. I changed the test helpers to build the
  22 real ids from `branding.DISPLAY_NAMES`, which also makes the caption test
  exercise the real mapping.

### What I changed and why
- `src/branding.py` (new): `DISPLAY_NAMES`, `FUSION_DISPLAY_NAMES`,
  `VOL_TARGET_DISPLAY_NAMES`, `FUSION_BASE_FUND`; `fund_display_name(fund_id)`
  resolves base funds and the `_base` / `_vol_targeted` / `_momentum` /
  `_contrarian` variant rows (raises `KeyError` on unknown ids); 
  `display_names_table()` builds the full 29-row lookup; 
  `family_display_prefix(family)` derives e.g. "Invesper US Equity" from the
  family's names for titles; `wrap_display_name()` wraps at word boundaries.
- `src/plots.py`: `fig_metrics_table` (display names, wrapped, wider figure),
  `fig_growth_of_1` (legend = per-fund display names; title uses the
  family's shared prefix, e.g. "Invesper US Equity funds - growth of $1"),
  `fig_sharpe_barplot` (wrapped display names at rotation 55 / fontsize 6.5 /
  figsize 14x6; family legend now uses `FAMILY_LABELS`), `fig_growth_groupings`
  (legend = display names), `fig_fusion_growth` (legend = base / (Momentum) /
  (Contrarian) display names), `fig_vol_target_growth` (legend = base name +
  "(Managed Vol)"), `fig_vol_target_scaling` (title = "(Managed Vol)" name),
  `fig_drawdown` / `fig_weights_stacked` (title = display name; optional
  `fund_id` kept in the caption for CSV traceability).
- `scripts/run_part_b.py`: new `save_display_names()` writes
  `results/data/fund_display_names.csv` (29 rows) in `main()`; figure calls
  now pass display names and keep technical ids in captions.
- `tests/test_smoke.py`: `_build_metrics` / `_build_returns_long` now build
  the 22 real ids from `branding.DISPLAY_NAMES`; new
  `test_fund_display_names_cover_every_id` asserts the CSV has exactly the
  `fund_id`/`display_name` columns, matches `branding` exactly, and covers the
  union of every `fund` value in all five results CSVs. (23 -> 24 tests.)

### Judgement calls
- **CSV scope**: the prompt says "generated from this dict"; I generated it
  from the full mapping (22 base + 7 variant rows) so the app can look up ANY
  `fund` value it might encounter, not just the 22 base ids.
- **Captions stay technical**: `fig_drawdown` / `fig_weights_stacked` /
  vol-target captions now cite the technical fund id (e.g. `(combined_max_sharpe)`)
  for CSV traceability, while titles show the display name.
- Fusion legend labels drop the old "(lambda=+1/-1)" notation in favour of the
  investor names; the lambda rule is still documented in the caption.

### Result (recomputed from the regenerated CSVs; all figures/CSVs re-run)
- `results/data/fund_display_names.csv` written by the pipeline (29 rows,
  `fund_id` + `display_name`).
- Every display-name figure regenerated; OCR-verified on the rendered PNGs:
  fusion growth (title + all three legend names + end labels $1.25/$1.23/$1.14),
  vol-target growth (title + base/(Managed Vol) legend + $1.27/$1.13 end
  labels), vol-target scaling (Managed Vol title), drawdown, weights,
  growth_of_1_{equity,sector_clusters,crypto_themes} (display-name legends;
  end-label values unchanged), performance_metrics_table (all 22 wrapped
  display names, metrics values unchanged).
- Layout check across all 10 display-name figures: 0 tick-label collisions, 0
  truncations, no label/caption overlap.
- Backtest numbers unchanged by design (presentation-only change): 24 tests
  pass; ruff clean on `src/branding.py`, `src/plots.py`,
  `scripts/run_part_b.py`, `tests/test_smoke.py`.

### Files
- `src/branding.py` (new - the mapping and helpers)
- `src/plots.py` (display-name rendering everywhere human text appears)
- `scripts/run_part_b.py` (`save_display_names`, figure calls)
- `tests/test_smoke.py` (real-id synthetic fixtures + coverage test; 23 -> 24)
- `results/data/fund_display_names.csv` (new, 29 rows)
- `results/figures/*` (all 16 PNGs regenerated)
- `README.md` (this section + branding note)

---

## Entry 9: Station 4 first pass - the Streamlit app (Prompt 04)

### What I wanted
A working first-pass Station 4 app in `streamlit_app.py` (folder root,
replacing the stub) covering the brief's four required user actions using only
precomputed data: Compare funds, Fund fact sheet, Sentiment analytics, Build an
allocation. Non-negotiables: no backtest/optimiser/sentiment code anywhere in
the app or anything it imports; every fund label from
`results/data/fund_display_names.csv` (never a raw id); cached data loads;
Equity / Crypto / Multi-Asset universe split of 12 / 9 / 5.

### Prompt(s)
Prompt 04: build the four sections, derive the universe groupings
programmatically (family prefix) rather than hardcoding fund names, read the
prompt log/README/branding first, run `streamlit run` and confirm it loads,
log anything real that came up, update README.

### What the assistant produced / what I found
- **`app/data.py`** (new pure data layer, no streamlit import): reads the seven
  results CSVs, derives the universe grouping from the data, builds a unified
  metrics table keyed by fund id (with the source CSV per row), and implements
  the blend / drawdown / gauge math. Unit-testable without a browser.
- **`streamlit_app.py`** replaced the stub with four tabs; every figure is
  built live from the CSVs with Plotly: per-universe Sharpe bar chart + metrics
  table (Compare), growth-of-$1 + drawdown + current-holdings + four headline
  metrics (Fact sheet), sector sentiment lines + fear/greed gauge + the
  embedded `sentiment_lexicon_comparison.png` (Sentiment), and blended
  gross/net growth with the zero-commission pricing line next to the fee input
  (Allocation).
- **Universe derivation matched the prompt exactly** (Equity 12 / Crypto 9 /
  Multi-Asset 5, pinned by a test). Membership is data-driven: family ->
  universe comes from the `family` column of `performance_metrics.csv`; fusion
  variants (momentum/contrarian) are always Equity; vol-targeted variants
  inherit the universe of their base fund (resolved via the metrics CSV). Only
  the family/method sort order is constant. The `{base}_base` duplicate rows in
  the comparison CSVs are excluded so no fund appears twice.
- Display names come from the CSV only (no `src.branding` import in the app, as
  established for anything app-facing); a test asserts no universe id's display
  name equals its raw id.

### What was wrong or risky
- **AppTest caught a real, user-reachable bug on the first run**: the
  allocation slider loop labelled each slider `options[fund]`, but `options`
  maps display name -> id, so picking a fund raised
  `KeyError: 'equity_equal_weight'`. The default app view is fine; the crash
  only happens after a user selects funds — exactly why the workflow requires
  exercising every active view, not just the default tab.
- Streamlit 1.58 deprecates `use_container_width` (warnings in the test log);
  replaced everywhere with `width="stretch"`.
- My first AppTest also assumed `at.plotly_chart` / `at.image` accessors exist;
  in this version they are `at.get("plotly_chart")` and `at.get("imgs")`.

### Judgement calls
- **Fact sheet for the 4 variants** (momentum/contrarian/2x vol-targeted): their
  daily return series and weights are NOT published under `results/` (Station 3
  saves only their summary metrics), so growth/drawdown/holdings cannot be built
  without re-running a model (forbidden). The fact sheet shows their four
  headline numbers from the right comparison CSV plus an explicit note that the
  return-history views exist for the 22 base funds only. Omitting the variants
  from the dropdown instead would have contradicted the prompt's 12/9/5
  enumeration.
- **Allocation blends the 22 base funds only** (the published return series);
  variants are excluded from the picker for the same no-model reason.
- **Calendar alignment in the blend**: returns are aligned on the union of each
  fund's calendar; a date a fund has no row for counts as 0% return (market
  closed). Handles equity funds on crypto weekend days without ffill (which
  would incorrectly carry Friday's return into the weekend).
- **Fee mechanics**: charged daily on AUM at `fee/365`, so the net-vs-gross gap
  is visible; 0.5% default (placeholder per the prompt). The pricing line states
  Invesper's zero-commission framing next to the input.
- **Gauge rescale**: the 0-100 fear/greed scale rescales the equal-weighted
  sector index across the FULL published sample, stated in the caption along
  with a warning that the scale moves if the sample changes (composite-indicator
  rule).
- **Market sentiment uses the `sentiment_aligned` display column**; the caption
  notes the investable signal is lagged one trading day.
- Compare/fact sheet use radio + dropdown for the universe split (prompt left it
  to me).

### Result (verified by running the app, not just syntax)
- `streamlit run streamlit_app.py` starts headless (health endpoint 200).
- `st.tabs` renders all bodies eagerly, so one AppTest run exercises all four
  sections; 5 AppTest tests (loads all tabs, compare universe switch, variant
  fact-sheet note, base fact-sheet charts, allocation blend with fee) plus 17
  data-layer tests (universe sizes/composition/disjointness, display-name
  coverage, no unclassified ids, metrics sources, drawdown traceability to
  `performance_metrics.csv` to 1e-4, blend math incl. fee reduction, gauge
  bounds, holdings sorted). Total suite: **46 tests pass**; ruff clean on
  `app/`, `streamlit_app.py`, `tests/`.
- Drawdown recomputed in the app matches the committed CSV exactly
  (e.g. `combined_equal_weight` -0.2875); no `src.*` or `nltk` import anywhere
  in `streamlit_app.py` / `app/data.py` (grep-verified).

### Files
- `streamlit_app.py` (stub replaced; four tabs)
- `app/__init__.py`, `app/data.py` (new pure data layer)
- `tests/test_app.py` (new, AppTest), `tests/test_app_data.py` (new, pure)
- `requirements.txt` (+plotly for the app)
- `results/` (unchanged - the app reads the committed CSVs)
- `README.md`, `ai/AI_NOTES.md` (updated)

---

## Entry 10: Make the 4 extension variants fully interactive (Prompt 05)

### What I wanted
The 4 variants (`equity_min_variance_momentum`, `equity_min_variance_contrarian`,
`combined_max_sharpe_vol_targeted`, `crypto_max_sharpe_vol_targeted`) were the
innovation-band work but existed in the app only as summary rows — their daily
return series was computed in memory during the pipeline and never saved, so the
fact sheets showed a "no published return history" note and the allocation
builder excluded them. Fix it properly: persist the series, give fusion variants
real weight rows, fall the vol-targeted variants back to their base fund's
holdings, and surface all 4 everywhere in the app.

### Prompt(s)
Prompt 05 (full text in `ai/prompts/prompt_05.md`): append the 4 variant daily
return series to the SAME `fund_returns.csv`; append the fusion tilt weight
series to `fund_weights.csv`; do NOT duplicate weight rows for the vol-targeted
variants (app falls back to the base fund with an explanatory caption); remove
the special-case note; add all 4 to the allocation picker; add the gauge
unlagged caption; update tests; re-run pipeline + app + suite + ruff.

### What the assistant produced / what I found
- **Pipeline** (`scripts/run_part_b.py`): the fusion daily returns and tilt
  weights already existed in memory (`fu.run_fusion` returns both) and the
  vol-target scaled returns already existed (`vt_parts[label][1]`). I reordered
  `main()` so fusion/vol-target run BEFORE the CSV save, then
  `save_funds_and_metrics` appends them to the same long tables:
  - `fund_returns.csv`: 19302 -> 22656 rows (26 fund ids).
  - `fund_weights.csv`: 21528 -> 25128 rows (24 fund ids: 22 base + 2 fusion;
    vol-targeted deliberately absent).
- **Fusion granularity**: the tilt is recomputed at the base fund's own MONTHLY
  rebalance dates (the `tilt_weights` loop iterates `base_weights.index`, the
  same monthly grid as every other fund) — NOT a daily-updating tilt. So the
  persisted weight rows use the exact `fund_weights.csv` schema with the same
  rebalance dates, and `latest_holdings` in the app works unchanged (no
  "most recent available date" wrinkle was needed). I set
  `fused.index.name = "date"` in `tilt_weights` to match the
  `portfolios.oos_backtest` convention the writer relied on.
- **App**: the fact-sheet early-return note is gone; the 4 variants render the
  full growth/drawdown/4-metrics/holdings views like every other fund. The
  vol-targeted variants get a caption:
  "Volatility targeting scales overall exposure, not individual holdings -
  shown here are the underlying {base fund's display name}'s holdings." The
  allocation picker now lists all 26 funds (derived, not hardcoded). The gauge
  caption now states: "Current reading (unlagged) - for display only; fund
  construction uses the lagged signal shown in the sector chart." (column
  unchanged, as the prompt required).

### What was wrong or risky
- **The gauge column distinction is now explicit rather than implied** — the
  prompt noted the gauge reads `sentiment_aligned` (unlagged) while fund
  construction uses lagged `sentiment`; no look-ahead exists because the gauge
  feeds no decision, but the caption makes the distinction visible.
- My first AppTest assertions were wrong in a way the test suite caught: I
  expected the variant fact sheet to ADD 2 charts on top of the default view.
  In fact the default base fund already renders the same 3 fact-sheet charts,
  so selecting a variant keeps the total at 6. The correct regression check is
  that the count does NOT drop to 3 (the old early-return behaviour): a variant
  must render as many charts as a base fund, plus the vol-target holdings
  caption.

### Judgement calls
- **Vol-targeted variants still get no weight rows** (per the prompt): the
  overlay is a portfolio-level scalar `k_t`, so duplicating the base fund's
  rows would be misleading and would break the "sum to 1 at every rebalance"
  invariant implied by `fund_weights.csv`. The app resolves holdings via
  `app.data.base_fund_of`.
- **The pipeline reorder** (vol-target/sentiment/fusion before the CSV save)
  is invisible to the figures (still 22-fund Station 3 exhibits) but required
  so the appends reference in-memory series rather than reloading.
- **Safety net kept**: the fact sheet still guards an empty return series with
  a neutral "rerun the pipeline" info instead of crashing (only reachable on a
  stale `results/`).

### Result (verified by running the app, not just syntax)
- `streamlit run streamlit_app.py` starts headless (health 200). 7 AppTest
  tests exercise all four tabs including both variant fact-sheet flows and a
  variant-bearing allocation; drawdown recomputed in the app matches the
  committed `fusion_comparison.csv`/`vol_target_comparison.csv` to 1e-4 for
  all 4 variants (new data-layer test); fusion tilt weights sum to 1 with
  monotone-decreasing holdings; no vol-targeted rows exist in `fund_weights.csv`.
- Full suite: **53 tests pass**; ruff clean on `app/`, `streamlit_app.py`,
  `src/fusion.py`, `scripts/run_part_b.py`, `tests/`.
- Pipeline re-run reproduces everything (fund_returns 22656 / fund_weights
  25128 / metrics 22 / fusion 3 / vol-target 4 / display names 29).

### Files
- `scripts/run_part_b.py` (reordered `main()`, `save_funds_and_metrics` appends variants)
- `src/fusion.py` (tilt weights get `index.name = "date"`)
- `app/data.py` (`base_fund_of` helper + comments)
- `streamlit_app.py` (fact-sheet note removed, vol-target holdings caption,
  allocation caption/count, gauge caption)
- `tests/test_app.py` (variant fact-sheet + allocation-variant + gauge-caption tests)
- `tests/test_app_data.py` (variant series + drawdown traceability + weights tests)
- `tests/test_smoke.py` (traceability test accounts for the 4 appended series)
- `results/data/fund_returns.csv`, `results/data/fund_weights.csv` (regenerated)
- `README.md`, `ai/AI_NOTES.md` (updated)

---

## Entry 11: Prompt 06 - design/polish pass + a user-mandated annualisation correction

### What I wanted
Prompt 06 (`ai/prompts/prompt_06.md`) asked for a design/polish pass on the
Station 4 app:
1. Long-form dates (`01 January 2021`) at every point-in-time **text** site,
   via a single shared helper - chart axis ticks untouched.
2. Humanised metric labels ("Sharpe Ratio", "Max Drawdown", ...) via one
   lookup dict, not per-call-site strings.
3. Compare tab's Sharpe chart turned **horizontal** (y = display names, sorted
   descending), per-universe as before.
4. Fear/greed gauge wording tightened to "0 = Fear - 100 = Greed".
5. Sentiment tab: drop the embedded PNG and render the VADER-vs-finVADER
   comparison natively in Plotly, built entirely from a small precomputed
   summary CSV - the app must never load the 146,836-row per-headline table.
6. Replace the editable fee input with the **real 26-entry fee schedule**:
   `FEE_SCHEDULE` lives in `src/branding.py`, the pipeline writes
   `results/data/fund_fees.csv`, the allocation tab shows each fund's fee next
   to its weight slider plus a weighted blended fee.
7. A **Portfolio tab**: "submit" the current allocation and it is saved as a
   session-only portfolio (name auto-uniquified) with a donut chart, gross vs
   net growth, four headline metrics, and delete; a session-only caption.

### Prompt(s)
Prompt 06 (full text in `ai/prompts/prompt_06.md`), plus a mid-implementation
correction from the student (see the dedicated section below) about how the
Portfolio tab annualises the blended series.

### What the assistant produced / what I found
- **`app/formatting.py`** (new): `METRIC_LABELS`, `format_date(value) ->
  "%d %B %Y"`, `metric_label(column)` - the single source for both tasks 1-2.
- **`app/data.py`**: `required_files()` now also expects `fund_fees.csv` and
  `sentiment_lexicon_comparison_summary.csv`; new `load_fund_fees()`,
  `load_sentiment_lexicon_summary()`, `blended_fee(weights, fees)`,
  `annualisation_factor(index)` and `portfolio_metrics(growth)`; `AppData`
  gains `fees` + `lexicon_summary` and drops the `lexicon_figure` PNG path.
- **`src/branding.py`**: `FEE_SCHEDULE` with the exact 26 fee values and
  `fees_table()` producing the `fund_id`/`fee_annual` frame.
- **`scripts/run_part_b.py`**: new `save_fund_fees()` and
  `save_sentiment_summary()`; the summary CSV carries three row types
  (monthly_mean 96, histogram 120, neutral 1 = 217 rows).
- **`streamlit_app.py`**: fifth "Portfolio" tab; horizontal, sorted Sharpe
  chart; `format_date` at every text-date site; native Plotly lexicon chart;
  per-fund fee captions + blended-fee caption (fee input removed); Portfolio
  tab with per-name Plotly keys, rotating name-input key, delete + rerun.
- **Tests** rewritten/extended: five tabs, `imgs == 0`, plotly count >= 7, no
  `number_input` in the allocation, per-fund fee captions + blended-fee
  markdown, portfolio save/list/delete flow, summary-CSV reproduction test,
  fee/blended-fee unit tests, annualisation/metrics unit tests.

### What was wrong or risky (things the tests or review caught)
1. **`np.histogram` edges vs counts.** `np.linspace(-1, 1, 61)` creates 61
   *edges* -> 60 bin *counts* per lexicon, but my first test asserted 61 rows
   per lexicon. The summary CSV is correct at 60; the test was fixed to 60.
2. **Streamlit 1.58 duplicate-element guard.** Saving a second portfolio made
   two donut/growth charts render, which raised
   `StreamlitDuplicateElementId` (duplicate auto-generated `plotly_chart`
   ids). Fix: explicit per-name `key=` on both Portfolio charts. (Side note
   learned: `st.metric` does **not** accept a `key` argument in this Streamlit
   version, so the four headline metrics cannot take one - no duplicate risk
   there.)
3. **Reused text-input key.** The portfolio-name field kept one static key, so
   the second submit silently reused the first portfolio's name. Fixed by
   rotating the widget key per submit.
4. **The summary-reproduction test** compared `Series.equals`, which also
   compares index dtype (`datetime64[us]` vs `ns`) and series name; changed to
   a value-level `pytest.approx` comparison after reindexing.

### Correction applied during review: empirical annualisation for blended portfolios
The student reviewed the new Portfolio tab and rejected hardcoding
`sqrt(252)` for the blended gross/net series:

- **What was wrong.** `portfolio_metrics` annualised the user's blended series
  with the flat equity factor 252. But `blend_portfolio` aligns funds on the
  **union** of their calendars, so a crypto-inclusive portfolio trades on
  crypto's ~365-day calendar while a pure-equity portfolio trades on ~252
  days. A single hardcoded 252 was wrong for every mix by a different amount,
  and the whole point of a session-only portfolio tab is that the mix is
  arbitrary.
- **Why it matters.** Annualised volatility (and therefore the headline Sharpe
  ratio) is scaled by the factor: an over-small factor like 252 on a ~365-day
  series understates annualised volatility by ~20% (`sqrt(365/252)`), which
  silently flatters risk-adjusted performance for any crypto-inclusive
  portfolio and misreports the factor in the caption as a fixed "252".
- **What changed.** `annualisation_factor(index)` now derives the factor
  **empirically per portfolio** as `observed_trading_days / (span_days /
  365.25)` on the blend's own date-union index; `portfolio_metrics` uses it for
  all four headline numbers and reports it; the Portfolio tab caption states
  it ("Annualised using this portfolio's actual observed trading calendar (~X
  days/year)"). Published fund metrics are untouched - the backtest still
  annualises equity/combined at sqrt(252) and crypto at sqrt(365), because
  those series each live on one homogeneous calendar. Tests pin the behaviour:
  a pure-equity blend's factor is ~252, a 50/50 equity+crypto blend's factor is
  higher and bounded by the calendar-span math (<= 370, not <= 365, because
  the 2020-2023 span includes leap days), and `portfolio_metrics` uses the
  factor consistently (mean x factor, ddof=1 std x sqrt(factor), sharpe,
  drawdown <= 0, total return).

### Result (verified end to end)
- `python scripts/run_part_b.py` runs clean end to end; the regenerated
  `fund_fees.csv` has exactly the 26 schedule rows (fees sum to 0.1135) and
  `sentiment_lexicon_comparison_summary.csv` has 217 rows (monthly_mean 96 +
  histogram 120 + neutral 1).
- `python -m pytest -q tests/`: **65 tests pass** (was 53 before prompt_06).
- Headless `streamlit run` boots and the `/_stcore/health` endpoint returns
  OK; an AppTest click-through saves, lists and deletes portfolios.
- Ruff clean on every changed file. The only remaining `ruff check .` findings
  are the two pre-existing style items in `src/data_access.py`, which is the
  course-provided frozen helper ("PROVIDED - do not edit") - left untouched by
  design.

### Files
- `app/formatting.py` (new), `app/data.py` (fees, lexicon summary, blended
  fee, annualisation factor, portfolio metrics)
- `src/branding.py` (`FEE_SCHEDULE`, `fees_table`),
  `scripts/run_part_b.py` (`save_fund_fees`, `save_sentiment_summary`)
- `streamlit_app.py` (5th tab, horizontal Sharpe, format_date, native lexicon
  chart, fee captions, Portfolio tab)
- `tests/test_app.py`, `tests/test_app_data.py` (new/updated; 53 -> 65)
- `results/data/fund_fees.csv` (new, 26 rows),
  `results/data/sentiment_lexicon_comparison_summary.csv` (new, 217 rows)
- `README.md`, `ai/AI_NOTES.md`, `AGENTS.md`, `CLAUDE.md` (updated)

## Entry 12: Drop the lexicon comparison from the app; fix a real Plotly crash; logo beside the title

### What changed and why
After prompt_06 shipped the VADER-vs-finVADER-lite chart inside the Sentiment
tab, review moved the lexicon comparison **out of the app entirely**: the
precomputed summary CSV stays in `results/` for the report, but the running app
no longer reads it. The Sentiment tab now shows the sector index lines and the
fear/greed gauge only - a smaller, faster app surface with one less precomputed
artifact to keep in sync. This reverses prompt_06 item 5's "native lexicon
chart in the app".

- **`app/data.py`**: removed `load_sentiment_lexicon_summary()`, the
  `AppData.lexicon_summary` field, its builder call, and the
  `sentiment_lexicon_comparison_summary.csv` entry in `required_files()`.
- **`streamlit_app.py`**: no Sentiment-tab lexicon chart; module docstring
  updated to say the summary stays in `results/` for the report.
- **Tests**: the two lexicon-summary tests in `tests/test_app_data.py`
  (`test_sentiment_lexicon_summary_shape`,
  `test_summary_csv_matches_headline_sentiment`) were removed and replaced with
  a guard, `test_app_never_reads_lexicon_summary`, asserting neither
  `streamlit_app.py` nor `app/data.py` references the loader, the CSV, or the
  field again (same pattern as the existing `headline_sentiment` guard).

### Bug found by running the app: `yaxis.categorygap` is not a valid Plotly property
While smoke-testing the app after the removal, `streamlit run` crashed on the
Compare tab:

- **Symptom.** `ValueError: Invalid property specified for object of type
  plotly.graph_objs.layout.YAxis: 'categorygap'`. The whole app failed to
  render past the first tab.
- **Root cause.** Plotly only defines `categorygap` on the **x** axis. The
  Compare-tab Sharpe chart is a *horizontal* bar (`orientation="h"`, long
  display names on y), so its category axis is y - and the prompt_06 layout
  code had set `yaxis.categorygap` to widen the gap for wrapped labels. Every
  test in the previous pass was green because AppTest renders tabs lazily; the
  layout call only fired when the Compare tab actually ran.
- **Fix.** Removed `categorygap` from the `yaxis` dict (the dynamic
  `height=240 + 45 * len(...)` already keeps wrapped labels separated); comment
  notes plotly's x-only `categorygap`. Verified with an AppTest that drives the
  Compare tab through all three universes.
- **Process lesson logged.** AppTest's tab elements are not rendered until
  switched to, so a crash confined to one tab can pass `_app().run()` + the
  global "no exception" assertion. The `test_compare_switches_universe` test
  exists precisely to force each universe; it caught nothing here because the
  crash was in the layout call, not the universe switch. To be safe, the
  tab-switching tests assert `not at.exception` after every `.set_value(...)`
  re-run, which does catch a crash on any tab path actually taken.

### Logo placement
Per student feedback the header `st.logo` badge (Streamlit 1.58 caps it at
32px even on "large", so it reads as a barely-visible corner icon) was replaced
with the logo rendered inline beside the page title: `main()` now lays out
`st.columns([1, 6], vertical_alignment="center")` with the logo image on the
left and `st.title("Invesper Systematic Funds")` on the right. An earlier
attempt at a large `st.sidebar.image` banner was rejected by the student (no
side menu wanted) and reverted. Test updated: `test_app_loads_all_five_tabs`
now expects exactly one `img` (the title-row logo) instead of zero.

### Result
- `python -m pytest -q tests/`: **64 tests pass** (was 65 after prompt_06;
  -2 lexicon tests, +1 guard, net -1).
- App boots cleanly; Compare tab renders all three universes with no exception.
- Ruff clean on every changed file (`streamlit_app.py`, `app/data.py`,
  `tests/test_app.py`, `tests/test_app_data.py`). The two pre-existing
  `src/data_access.py` style findings remain untouched (frozen provider file).

### Files
- `app/data.py` (removed lexicon loader + field + required-file entry)
- `streamlit_app.py` (dropped lexicon chart; `yaxis.categorygap` fix; logo
  beside title via columns)
- `tests/test_app_data.py` (dropped 2 lexicon tests, added
  `test_app_never_reads_lexicon_summary`)
- `tests/test_app.py` (plotly count 7 -> 6; imgs 0 -> 1 for the title logo)
- Docs: `README.md`, `AGENTS.md`, `CLAUDE.md` (removed "app loads the lexicon
  summary" wording; Sentiment-tab and results-table descriptions updated)

## Entry 13: Prompt 07 - git repo, hand-in check, and private GitHub push

### What changed and why
Prompt 07 turned the project folder into a real submission repo: its own git
repo (isolated from the enclosing `fins-agent` course repo), a clean hand-in
check, and a private GitHub remote. All code plus the precomputed app
artifacts under `results/` are committed; raw data and secrets are not.

### `.gitignore` before / after
- **Before:** already correct in substance - `__pycache__/`, `*.pyc`, `.venv/`,
  `venv/`, `data/`, `*.parquet`, `*.csv`, `.streamlit/secrets.toml`, `.env`
  ignored, with `!results/**` and `!src/lexicons/**` carve-outs. The lexicons
  are committed on purpose (LM grounding dictionary + our finVADER-lite
  extension; the sentiment pipeline reads them at runtime).
- **After:** added `.pytest_cache/` and `.ruff_cache/` to the Python ignore
  block (standard CI noise that should never be staged). No image rule exists,
  so `assets/*.png` commits normally - the prompt's "silent PNG catch" did not
  apply here.

### `check_handin.py` fix (the one `[FAIL]`)
Running the checker for real after committing flagged the lexicon CSVs as
"data files should not be committed", contradicting the brief and the
`.gitignore` carve-out:

- **Before:** the data-file scan excluded only paths containing `results`.
- **Fix:** `scripts/check_handin.py` now also exempts `src/lexicons/**` (path
  parts `src` and `lexicons`), mirroring `.gitignore`. The LM dictionary is a
  public reference lexicon and the extension is our own small addition - both
  are committed artifacts the pipeline needs, not raw project data.
- **Result:** `21 checks passed` with 2 reminders only (`__pycache__` cleanup
  before zipping; no `report/report.pdf` yet - the report is a later step).

### Repo creation
- `git init` at the project root (default branch **`master`**; user identity
  `Raynard Nicholas Thela <z5710071@ad.unsw.edu.au>`). `git rev-parse
  --show-toplevel` confirms the project repo is independent of the enclosing
  `fins-agent` course repo.
- Initial commit `6ca31e6`: 81 files, all code + tests + docs + `results/`
  (incl. figures) + `src/lexicons/*.csv` + `assets/*.png`. Staged review
  confirmed no raw data, no secrets, no caches.
- `gh` auth check: logged in as **`rayt737`** (`repo` scope, https). Remote
  created and pushed with `gh repo create z5710071_projectB --private
  --source=. --push`.
- **Repo: https://github.com/rayt737/z5710071_projectB** (visibility
  PRIVATE, default branch `master`, remote `origin` tracks `origin/master`).
- Verified against the remote: `results/data/*.csv`, `results/figures/*.png`,
  `results/tables/*.csv`, `src/lexicons/*.csv`, `assets/*.png`,
  `streamlit_app.py` all present; no `data/` folder and no secrets pushed.

### Result
- `scripts/check_handin.py`: **21 checks passed**, 2 reminders, 0 `[FAIL]`.
- Repo is private on GitHub; the student controls the visibility flip at
  hand-in time (see `docs/STUDENT_DEPLOY.md`).
- Working tree clean after the commit; nothing else pending for this prompt.

### Files
- `scripts/check_handin.py` (data-file scan now exempts `src/lexicons/**`)
- `.gitignore` (added `.pytest_cache/`, `.ruff_cache/`)
- `ai/prompt_log.md` (this entry)
