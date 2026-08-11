# Prompt 01 — Station 3 core build (funds, backtest, sentiment, fusion)

Context: this is Part B (Stations 3–4) of the FINS3645 FinTech project, built inside
this folder (`z5710071_projectB`). Part A (Stations 1–2) is already complete in my
separate `z5710071_projectA` folder and is the foundation this reuses. Before doing
anything, read, in this order:

1. `PROJECT_BRIEF.md` (this folder) — the authoritative spec.
2. `AGENTS.md` and `CLAUDE.md` (this folder) — replace their placeholder content
   with real working rules as you go; don't leave them as stubs.
3. `context/DATA_GUIDE.md` and `context/project_context.md`.
4. My completed Part A folder's `src/etl.py`, `src/features.py`, and
   `ai/SESSION_STATE.md` / `ai/learnings.md` — this is the logic to port in, not
   reference-only. Part A's `results/data/combined_returns_panel.csv` is only a
   200-row *sample* (Part A's brief required a sample, not the full file) — do not
   treat it as the full dataset. Rebuild the full panel here by re-running Part A's
   actual ETL/feature logic against the source data via `src/data_access.py`.

This prompt covers **Station 3 only**: the funds, the backtest, the sentiment index,
and the fusion baseline. Do **not** touch `streamlit_app.py` (Station 4 — a later
prompt) and do **not** build the additional structured-side extension (e.g. vol
targeting) yet — stop short of that and report back; we're deciding it together once
we can see real output from this build.

## Non-negotiables (apply everywhere)

- No look-ahead, anywhere: portfolio weights on day *t* are formed only from data
  strictly before *t*; the sentiment signal is lagged at least 1 trading day before
  it can influence a fund. Add explicit assertions that catch a violation, don't
  just rely on careful indexing.
- Long-only, fully invested: every fund's weights are `>= 0` and sum to 1 at every
  rebalance.
- Annualise equity and combined with `sqrt(252)`, crypto with `sqrt(365)`. Never
  difference price levels across the two calendars — returns are computed within
  each panel first (already true of Part A's output), combined = crypto returns
  left-merged onto the equity calendar.
- Assume risk-free rate = 0 (state this).
- Sanity-check the optimisers: min-variance, max-Sharpe, and risk parity must
  actually produce *different* weight vectors from each other and from equal-weight.
  If two methods collapse to near-identical weights, the solver has likely stalled
  below tolerance (a known trap on tiny daily-return covariances) — fix the scaling,
  don't silently accept it.
- Every number that will eventually appear in the report must trace back to one of
  the CSVs this build produces. Don't let any figure or table be built from a
  separately hand-computed number.
- Log real problems as you hit them in `ai/` (new files, following
  `ai/prompt_log_template.md`'s format) — e.g. a look-ahead bug you introduced and
  caught, a solver stall, a lexicon-agreement judgment call. This is graded
  (AI Workflow & Transparency, 20% of Part B) — don't skip it or write it
  retroactively as a summary; capture it while it happens.

## 1. Funds: build all 12

Three asset universes — **Equity** (50 stocks), **Crypto** (10 coins), **Combined**
(crypto left-merged onto the equity calendar) — each run through four optimisation
methods:

- **Equal-weight** — `w_i = 1/N`, no return/covariance input.
- **Minimum-variance** — `min_w w'Σw`.
- **Maximum-Sharpe (tangency)** — `max_w (w'(μ − rf·1)) / sqrt(w'Σw)`.
- **Risk parity** — solve for `w` such that every asset's risk contribution
  `RC_i = w_i(Σw)_i / w'Σw` is equal (`1/N` each).

That's 12 (family, method) funds. Put this in `src/portfolios.py`, one function per
method taking `(mu, cov)` → weights, plus a dispatcher.

## 2. Walk-forward out-of-sample backtest

- Expanding window. Initial estimation window = first year of daily returns.
- Rebalance monthly (first trading day of each month is fine — state your choice).
- First live/out-of-sample date is the first rebalance after the initial window
  (e.g. ~Jan 2021 if data starts ~Jan 2020) — state the actual date you land on;
  don't hardcode a date from the brief's example, derive it from the real data.
- Each month: use only data up to (not including) the rebalance date to
  re-estimate `μ`/`Σ`, set weights, hold them, earn the next month's realised
  return at those weights, then roll forward.
- Repeat to the end of the sample for all three universes.

Produce:
- `results/data/fund_returns.csv` — out-of-sample daily returns per fund (long or
  wide format, your call, but document which in `README.md`).
- `results/data/fund_weights.csv` — weights per fund per rebalance date per asset
  (this is also what "current holdings" on a fact sheet will read from later).

## 3. Performance metrics

For all 12 funds, compute annualised return, annualised volatility, Sharpe ratio,
max drawdown, total return, and turnover (mean absolute weight change at each
rebalance). Save as `results/tables/performance_metrics.csv` — this exact filename
and location, the app will read it later.

## 4. Required Station 3 exhibits (save to `results/figures/`, self-contained:
titled, labelled axes, units, sample period stated on the figure itself)

1. Performance-metrics table across all 12 funds (can reuse the CSV above,
   rendered cleanly for the report).
2. Growth of $1 — one figure per universe (equity / crypto / combined), all 4
   methods overlaid.
3. Drawdown figure for at least one fund (pick one that tells a clear story, e.g.
   the combined max-Sharpe fund, likely the most concentrated/volatile).
4. Portfolio weights over time (stacked area, by sector for equity/combined, with
   crypto shown as one band in combined) for at least one fund.
5. Sharpe (or return-vs-risk) barplot across all 12 funds.

If Part A established a plotting style/theme (check for a `src/style.py` or similar
in the Part A folder), reuse it for visual consistency across both reports. If none
exists, establish one now and use it consistently for every figure from here on.

## 5. Sentiment: VADER + a finance lexicon extension

Base: score every headline with VADER (`nltk.sentiment.vader`) on the **raw** text
(do not lowercase or strip punctuation — VADER needs capitalisation, punctuation,
and negation cues).

Extension — build a small, disciplined finance-lexicon addition, documented as you
go (this doubles as required AI-workflow evidence, not just a modelling step):

1. I've downloaded the Loughran-McDonald Master Dictionary CSV to
   `src/lexicons/Loughran-McDonald_MasterDictionary_1993-2025.csv` (86,553 words).
   Load it, keep only `Word` and the sentiment category columns (Negative,
   Positive, Uncertainty, Litigious, Strong_Modal, Weak_Modal, Constraining —
   drop Seq_num, Word Count, Word Proportion, Average Proportion, Std Dev, Doc
   Count, Complexity, Syllables, Source, none of that is needed). Note: each
   category column holds the **year the word was added to that category**
   (e.g. `LOSS` has `Negative = 2009`), not a 0/1 flag or a score — treat any
   nonzero value as "flagged in that category," don't use the year itself as a
   number. Use this as a grounding source for candidate terms, not as a
   ready-made VADER replacement.
2. Identify candidate finance-relevant terms: words that appear meaningfully often
   in the headline corpus, are flagged as Positive/Negative/Uncertainty in the LM
   dictionary, and are currently scored near-neutral by plain VADER (i.e. VADER is
   missing them). Keep this candidate list to a sensible size (tens, not thousands)
   — quality over volume.
3. Rate each candidate twice, independently, for a VADER-style valence in
   [-1, +1]: once as an initial pass, once as a second, differently-framed pass
   (e.g. re-ask with the term in isolation vs. in a sample headline context).
   Only keep a term in the final lexicon extension if the two ratings agree in
   sign and are reasonably close in magnitude; drop or flag disagreements rather
   than averaging them away silently.
4. Write the full candidate list, both ratings, the agreement outcome, and your
   reasoning to `ai/lexicon_extension_log.md` — this is a real deliverable, not
   throwaway scratch work.
5. Merge the agreed terms into VADER's lexicon dict and rescore all headlines with
   the extended lexicon (call it something like "finVADER-lite" or similar in
   code/comments, and note in the log that this is a novel small extension, not
   the pre-built `finVADER` PyPI package).
6. Produce a short before/after comparison (plain VADER vs. extended) — e.g. mean
   score shift, distribution of scores, or a time series like the Week 10 deck's
   comparison figure — as one of the sentiment exhibits.

## 6. Sector sentiment index

- Average scored headlines to one score per stock per day.
- Average stock scores within each sector, equal-weighting the stocks (state and
  justify how you handle stock-days with no headlines — drop, carry-forward, or
  treat as neutral; pick one and say why).
- Lag the resulting signal by **at least 1 trading day** before it's usable by any
  fund decision.
- Save as `results/data/sector_sentiment_index.csv` (exact filename, app reads it
  later).
- Produce the required sector-sentiment-over-time exhibit.

## 7. Fusion baseline (honest, not yet tuned)

Implement the tilt in `src/fusion.py`, applied to the **equity** minimum-variance
fund as the base (equity data only — sentiment does not touch crypto):

1. Standardise each stock's sentiment into a rolling z-score over a sensible
   window (state it), using sentiment up to day *t-1* only.
2. `w_tilt_i = w_base_i * (1 + λ * z_i)`.
3. Clip negatives to 0 and renormalise to sum to 1.

Run this at two honest, untuned settings — momentum (`λ = +1`) and contrarian
(`λ = -1`) — out of sample, before transaction costs. Don't tune λ here; that's
future work if we decide to pursue it. Report both against the untilted base
fund's Sharpe, whichever way it goes (a fusion that underperforms, clearly
explained, is fine — that's explicitly how the brief and the Week 10 deck frame
this baseline).

Produce:
- `results/tables/fusion_comparison.csv` — base vs. fused Sharpe/return/vol for
  both λ settings.
- A before/after growth-of-$1 or Sharpe comparison figure.

## 8. Orchestration & sanity checks

- Wire all of the above into `scripts/run_part_b.py` so it runs end-to-end from a
  clean checkout (load data → funds → backtest → sentiment → fusion → save
  everything above) and prints a summary table of all 12 funds' Sharpe ratios plus
  the fusion comparison to the console when done.
- Add assertions/tests (extend `tests/test_smoke.py` if useful) that catch: any
  fund's weights not summing to ~1, any negative weight, any rebalance using data
  from on-or-after its own decision date, and the four methods within a universe
  actually differing from each other.
- Do not run `scripts/check_handin.py` for real yet — it will fail on Station 4
  items that don't exist yet. That's expected and fine at this stage.

## Stop here and report back

Don't start Station 4 (the app) and don't build the additional structured-method
extension (e.g. volatility targeting) yet. When this is done, tell me: the
resulting Sharpe ratios across all 12 funds, anything that looked unstable or
surprising (solver behaviour, sentiment coverage/no-news-day frequency, how many
lexicon terms passed the agreement check), and anything you had to deviate from
this prompt on and why.
