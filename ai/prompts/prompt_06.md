# Prompt 06 — App design/polish pass + management fees + Portfolio tab

Station 4's four required sections all work and are fully tested. This is a
design/polish pass plus one real product feature (per-fund management fees
replacing the current user-set fee input) and one new section (a Portfolio
tab). Read `ai/prompt_log.md` in full first, and skim `app/data.py` and
`streamlit_app.py` before changing anything, so you're working with the
actual current structure, not an assumed one.

## 1. Date formatting

Any **point-in-time date shown as text** (fact sheet "as of" lines, "most
recent rebalance: ...", sample-period captions, anything similar) should
read as `01 January 2021`, not `2021-01-01`. Add one shared formatting
helper (e.g. in `app/data.py` or a small new `app/formatting.py`) and use it
everywhere a single date is rendered as text in the app — don't hand-format
dates individually per call site.

**Do not** apply this to chart axis ticks — a 3-year daily/monthly x-axis
written out in full ("01 January 2021" per tick) would be unreadable and
cramped. Chart axes should stay compact (e.g. "Jan 2021" / whatever
Plotly's default date-axis formatting already produces is fine — leave axis
tick formatting alone unless it's currently doing something actively wrong).

This is scoped to the live app. If any *static* Station 3 figure caption
also uses the short date format and it's a trivial change while you're in
the area, fine to fix, but it's not required — don't spend real time
regenerating Station 3 figures for this.

## 2. Humanize column/metric labels

Anywhere a raw column name like `sharpe_ratio`, `max_drawdown`,
`annualised_return`, `annualised_volatility` is currently shown to the user
as a table header or label, replace it with a human label ("Sharpe Ratio",
"Max Drawdown", "Annualised Return", "Annualised Volatility", etc.). Add a
small lookup dict alongside the existing `branding.py` fund-display-name
pattern (either in `branding.py` itself or a new small module) rather than
hardcoding the mapping per call site.

## 3. Fix the Compare tab's Sharpe barplot

The current dynamic Plotly Sharpe chart has rotated, overlapping fund-name
labels and reads as unpolished. Rebuild it as a **horizontal bar chart**
instead — Sharpe ratio on the x-axis, fund display names on the y-axis,
sorted by Sharpe value (descending is fine) — which sidesteps the
label-rotation problem entirely regardless of how long the display names
are. This only affects the app's own dynamically-built chart; the static
Station 3 `sharpe_barplot.png` already went through its own layout-fix pass
earlier and doesn't need touching.

Keep this **per-universe** — the Compare tab currently builds one Sharpe
chart per universe tab (Equity/Crypto/Multi-Asset, matching that universe's
own fund list), and that structure stays; this only changes each of those
charts from vertical/rotated to horizontal, not how many charts there are
or what funds appear in each.

## 4. Gauge label wording

Wherever the market-wide sentiment gauge currently shows "Fearful"/"Greedy"
(or similar), change the labels to just "Fear" / "Greed".

## 5. Rebuild the VADER-vs-finVADER comparison as a native chart

Currently this section embeds the static
`results/figures/sentiment_lexicon_comparison.png`, and its background
doesn't match the app's own background — it visibly sits in its own box.
Fix this at the root rather than patching around it:

- In `scripts/run_part_b.py` (or wherever the sentiment pipeline finalises
  its output), precompute a small **aggregated summary** from the full
  headline-level scores — monthly mean compound score for plain VADER vs.
  finVADER-lite, plus whatever score-distribution summary (e.g. binned
  histogram counts) is needed to reproduce the comparison — and save it as
  a new small CSV under `results/data/` (e.g.
  `sentiment_lexicon_comparison_summary.csv`). Don't load or process the
  full 146,836-row `headline_sentiment.csv` at app runtime — that's exactly
  why this was a static image in the first place, so precompute the summary
  once during the pipeline, not in the app.
- In the app, replace the embedded PNG with a native Plotly chart built from
  this small summary CSV, styled consistently with the rest of the app
  (transparent/matching background, not the Part A FT-style theme's tinted
  background).
- Add a test confirming the new summary CSV loads and the app doesn't import
  or read `headline_sentiment.csv` anywhere.

## 6. Per-fund management fees (replace the user-set fee input)

Letting a user freely set the management fee doesn't make sense — real fund
platforms price each fund according to its own strategy. Replace the fee
input entirely with a **fixed, tiered fee schedule** keyed by fund id, and
have the allocation builder show the resulting **weighted-average blended
fee** based on the user's actual fund selection and weights (not an editable
input).

Add this as `FEE_SCHEDULE` in `src/branding.py` (or a new `src/fees.py` if
that's cleaner), one fee (annual %, as a decimal) per fund id, using this
schedule — loosely inspired by real fund pricing (Vanguard-style passive
funds cheapest, actively-managed/thematic pricier, crypto priced at a
premium over equivalent equity strategies, the fusion/vol-target variants
priciest as the most "actively managed"):

```python
FEE_SCHEDULE = {
    # Core equity
    "equity_equal_weight": 0.0005,      # 0.05%
    "equity_min_variance": 0.0020,      # 0.20%
    "equity_max_sharpe": 0.0045,        # 0.45%
    "equity_risk_parity": 0.0030,       # 0.30%
    # Core crypto (priced at a premium over equivalent equity strategies)
    "crypto_equal_weight": 0.0025,      # 0.25%
    "crypto_min_variance": 0.0045,      # 0.45%
    "crypto_max_sharpe": 0.0075,        # 0.75%
    "crypto_risk_parity": 0.0055,       # 0.55%
    # Core multi-asset
    "combined_equal_weight": 0.0015,    # 0.15%
    "combined_min_variance": 0.0030,    # 0.30%
    "combined_max_sharpe": 0.0055,      # 0.55%
    "combined_risk_parity": 0.0040,     # 0.40%
    # Equity sector-cluster groupings
    "defensive_equal_weight": 0.0020,
    "defensive_risk_parity": 0.0035,
    "cyclical_equal_weight": 0.0020,
    "cyclical_risk_parity": 0.0035,
    "growth_sensitive_equal_weight": 0.0025,
    "growth_sensitive_risk_parity": 0.0040,
    # Crypto thematic groupings
    "payments_equal_weight": 0.0035,
    "payments_risk_parity": 0.0050,
    "web3infra_equal_weight": 0.0040,
    "web3infra_risk_parity": 0.0055,
    # Extension variants (most actively managed — priced highest)
    "equity_min_variance_momentum": 0.0085,
    "equity_min_variance_contrarian": 0.0085,
    "combined_max_sharpe_vol_targeted": 0.0075,
    "crypto_max_sharpe_vol_targeted": 0.0095,
}
```

Wire this into the allocation builder: remove the fee input widget entirely,
compute `blended_fee = sum(weight_i * FEE_SCHEDULE[fund_i])` from the
user's actual selection, display it clearly (e.g. "Blended management fee:
0.34% p.a."), and use it (not a flat default) for the net-of-fee growth
calculation. Show each selected fund's individual fee somewhere in the
allocation UI too (e.g. next to its weight input) so the blended number is
transparent, not a black box.

`app/data.py::blend_portfolio` already takes a single `fee_annual` argument
and does the gross/net growth math correctly (date-union handling, daily fee
accrual on AUM) — don't rewrite that function's blend logic. The only change
is *where* `fee_annual` comes from: computed from `FEE_SCHEDULE` and the
user's weights, instead of read from a UI widget.

## 7. New "Portfolio" tab — submit + save multiple built allocations

Add a final tab named "Portfolio". The Allocation tab keeps its live
preview (fund picker, weights, blended fee, gross/net growth) exactly as it
works now, but gets a **Submit** button at the end. Submitting:

- Prompts for a name for the portfolio (text input, auto-generate a
  reasonable default like "Portfolio 1" / a timestamp if left blank, and
  make sure names don't silently collide — auto-uniquify if needed).
- Saves the current allocation into `st.session_state` as a new entry in a
  list of saved portfolios: fund ids, weights, blended fee, **and the
  already-computed gross/net growth series itself** (store the actual
  computed values at submission time, not just the inputs needed to
  recompute them later — simpler, and avoids the saved portfolio's displayed
  numbers ever silently drifting if anything upstream changes). Don't
  reset/clear the Allocation tab's current working selection after submit —
  treat submit as "save a copy," so the user can keep adjusting and submit
  again as a different portfolio.

The **Portfolio** tab then lists every submitted portfolio (this session):
for each one, show its name, composition (fund names + weights — a small
donut/pie chart is a nice touch if easy, not required), its blended fee,
and its gross-vs-net growth-of-$1 chart with the same 4 headline metrics
used elsewhere (return/vol/Sharpe/max drawdown computed on the blended
series). Give each saved portfolio a delete button.

Be upfront in the UI about the real limitation here — add a visible caption
on the Portfolio tab: "Saved portfolios persist for this browser session
only and will reset if the app restarts or the page is reloaded." Streamlit
has no backend database here, so don't imply persistence beyond the session
— state it plainly rather than letting it look like more than it is.

## Important — this will break some existing tests/behaviour; expect and fix it

Based on how the app currently works, these specific things are almost
certainly going to break and need deliberate fixing, not just "run tests and
see":

- The existing allocation AppTest (the one exercising "gross/net growth")
  almost certainly interacts with the fee input widget you're removing in
  item 6 — it needs rewriting to reflect the new fee-schedule-driven flow,
  not left referencing a widget that no longer exists.
- There's an existing AppTest assertion on image count (`at.get("imgs")`)
  that currently expects `1` for the embedded VADER-vs-finVADER PNG — once
  item 5 replaces that with a native Plotly chart, this count needs updating
  (the image will be gone; a plotly_chart count elsewhere will go up
  instead).
- Item 1's date reformatting may break any existing test that asserts a
  specific ISO-format date string (`2021-01-04`-style) appears somewhere in
  rendered output — find and update those to expect the new long-form
  string instead of leaving them silently checking for text that no longer
  renders.
- After removing the fee widget, grep for any other place in the codebase
  that reads its old session-state key or variable name (not just the
  widget definition itself) and clean those up too.

## After

- Update/add tests in `tests/test_app_data.py` / `tests/test_app.py` for:
  the fee-schedule lookup and blended-fee calculation, the new sentiment
  summary CSV, and the Portfolio tab's save/list/delete flow (AppTest can
  drive session-state interactions — check how the existing app tests do
  this).
- Run the full pipeline, `streamlit run streamlit_app.py` locally to
  actually click through all changes (don't just trust the code), then the
  full test suite and ruff.
- Add a new entry to `ai/prompt_log.md` (existing format) — this is a real
  product/design pass worth documenting properly, including the fee
  schedule's rationale.
- Update `README.md` (`fund_display_names.csv`-style note for the new
  `FEE_SCHEDULE` and the sentiment summary CSV; mention the Portfolio tab
  and its session-only persistence caveat).

Report back: confirm all 7 items are done, the actual blended-fee numbers
for a sample allocation, and confirm the Portfolio tab's session-state
save/list/delete flow works end to end.
