# Prompt 04 — Station 4 first pass: the Streamlit app

Station 3 (funds, sentiment, fusion, vol-targeting, branding) is complete and
verified. This is the first pass at Station 4 — a working app covering the
brief's four required user actions, using only precomputed data. Read
`ai/prompt_log.md` in full first so you have the complete history (all the
bugs already caught and fixed), plus `README.md` and `src/branding.py`,
before writing any app code.

## Non-negotiables

- **Reads precomputed `results/` only.** No backtest, no portfolio
  optimisation, no VADER/nltk import, no re-scoring sentiment, anywhere in
  `streamlit_app.py` or anything it imports. Simple pandas aggregation of
  already-computed CSVs at runtime (e.g. averaging an already-lagged
  sentiment column across sectors for a summary figure) is fine — re-running
  any model is not.
- **Every fund label a user sees is a display name from `src/branding.py` /
  `results/data/fund_display_names.csv` — never a raw fund id** like
  `equity_max_sharpe`. Use the CSV lookup (not importing `src/branding.py`
  directly) since that's the pattern already established for anything
  app-facing.
- Cache data loads (`st.cache_data`) so the app stays responsive — this
  matters on Streamlit Community Cloud's free tier (~1 core).
- Entry point stays `streamlit_app.py` at the folder root (already exists as
  a stub — replace its contents, don't create a new file elsewhere).

## Navigation: three top-level universe groupings + a compare/fact-sheet flow

Everywhere a fund needs to be picked (Compare and Fact Sheet below), use the
same pattern: **Equity / Crypto / Multi-Asset** as the top-level grouping
(tabs or a radio selector, your call), then a dropdown of that universe's
funds. Sort each universe's funds like this:

- **Equity** (12 funds): the 4 core equity funds + the 6 sector-cluster funds
  (Defensive/Cyclical/Growth-Sensitive × equal-weight/risk parity) + the 2
  fusion variants (momentum/contrarian, built on equity min-variance).
- **Crypto** (9 funds): the 4 core crypto funds + the 4 crypto-theme funds
  (Payments/Web3 Infrastructure × equal-weight/risk parity) + the 1
  vol-targeted variant (crypto max-Sharpe, managed vol).
- **Multi-Asset** (5 funds): the 4 core combined funds + the 1 vol-targeted
  variant (combined max-Sharpe, managed vol).

Derive this grouping from the actual fund ids / `fund_display_names.csv`
programmatically where you can (e.g. family prefix) rather than hardcoding
every fund name as a literal list, so it doesn't silently drift out of sync
if anything changes later — but the 3-way universe split and which variants
belong where should match what's described above.

## 1. Compare funds

Within each of the three universe tabs: a performance-metrics table (return,
vol, Sharpe, max drawdown — pull from `performance_metrics.csv`,
`fusion_comparison.csv`, `vol_target_comparison.csv` as appropriate for that
universe's funds) and a Sharpe-ratio bar chart across that universe's funds,
built dynamically from the CSVs (not the static pre-rendered PNG, so it
stays consistent with whatever's in the data). Display names throughout.

## 2. Fund fact sheet

Pick a universe, then a fund from its dropdown. Show:
- Growth of $1 (line chart from `fund_returns.csv`, built dynamically).
- Drawdown (computed from the same return series).
- The four headline numbers: annualised return, annualised volatility,
  Sharpe ratio, max drawdown.
- Current holdings — a bar chart of target weights at the fund's most recent
  rebalance date, from `fund_weights.csv`.

Use the fund's display name as the fact sheet's title throughout.

## 3. Sentiment analytics

- Sector sentiment index over time — line chart from
  `sector_sentiment_index.csv`, with a sector selector (multi-select, default
  to all or a sensible few).
- A simple market-wide sentiment summary — average the sector index across
  sectors and present it as a single gauge/number (e.g. rescaled 0-100,
  "fear/greed" style, similar in spirit to the Week 10 deck's own example).
  This is a lightweight aggregation of an already-computed, already-lagged
  column — not a new model.
- The VADER-vs-finVADER-lite comparison — `headline_sentiment.csv` is large
  (146,836 rows), so embedding the already-rendered
  `results/figures/sentiment_lexicon_comparison.png` directly is fine here
  rather than rebuilding it from the raw CSV at runtime.

## 4. Build an allocation

- A multi-select letting the user pick any combination of funds across all
  three universes (not restricted to one universe — a user should be able to
  blend an equity fund with a crypto fund).
- A weight input per selected fund (sliders or number inputs), normalised to
  sum to 100% — show the user their current allocation sums correctly.
- A management fee input (annual %, simple default like 0.5% is fine as a
  starting point — this is a placeholder for now, not derived from
  anything).
- Show the blended growth of $1, gross and net of the fee, so the fee's
  effect is visible.
- Near the fee input, a short line establishing the product's pricing
  framing: Invesper charges no per-trade commission (consistent with the
  zero-commission model most modern brokerages/robo-advisors have adopted
  since 2019) and earns instead through this management fee on assets under
  management. Keep it to a sentence or two, not a marketing essay.

## After building

- Run `streamlit run streamlit_app.py` locally and confirm it actually loads
  and each of the four sections works — don't just confirm the code has no
  syntax errors.
- Don't run `scripts/check_handin.py` for real yet unless it happens to pass
  cleanly — deploy itself is a later step.
- Add a new entry to `ai/prompt_log.md` (existing format) for anything that
  came up — a real bug, a design decision worth recording (e.g. how you
  derived the universe groupings programmatically), or anything you deviated
  from this prompt on and why.
- Update `README.md`'s "What is here" / running instructions if anything
  about how the app is structured is worth documenting for a reader.

This is a first pass — functional and correct across all four required
sections, not final visual polish. We'll do a design/refinement pass once
this is running and I've actually seen it.

Report back: confirm all four sections work end to end, what the universe
fund-list derivation looked like, and anything that was ambiguous or needed
a judgement call.
