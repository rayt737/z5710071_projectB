# Prompt 02 — New fund groupings, growth-of-$1 end labels, vol-targeting overlay

Station 3's core 12 funds, sentiment, and fusion are done and verified. This
prompt adds three things: 5 new fund groupings, a plotting fix to match Part
A's growth-of-$1 style, and the volatility-targeting extension. Read
`ai/prompt_log.md` first so you have the full history of what's already been
built and fixed (solver stall, fund-id parsing, weights index, captions,
lexicon gap) — don't re-break any of it.

## 1. Five new fund groupings (equal-weight + risk parity only)

No market-cap data exists in this dataset (only price/volume), so these use
the two methods that don't need a return/risk estimate to be "fair" in that
sense — **equal-weight and risk parity only**, not the full four-method
matrix. Same walk-forward methodology as the existing 12 funds in every other
respect: expanding window, monthly rebalance, no look-ahead (same assertions),
long-only fully invested, correct annualisation for the universe.

**Three equity sector-cluster funds** (derive membership programmatically from
the `sector` column in `equity_prices` — don't hardcode ticker lists — filter
to each cluster's sector labels):

- **Defensive** — sectors `Healthcare`, `Utilities`, `Consumer`
- **Cyclical** — sectors `Financials`, `Industrials`, `Materials`, `RealEstate`
- **Growth/Sensitive** — sectors `Tech`, `Comm`, `Energy`

(This is adapted from the real Cyclical/Defensive/Sensitive super-sector
framework used by Fidelity/MSCI-style GICS groupings. Note in the code/log
that `Consumer` is placed in Defensive as a simplification — this dataset
merges Consumer Staples and Discretionary into one sector, so the placement is
a stated judgement call, not a textbook-exact mapping.)

Annualise these with `sqrt(252)` (equity calendar), same as the equity family.

**Two crypto thematic funds** (explicit ticker lists, BTC-USD excluded from
both — it stays only in the original 10-coin `crypto` universe funds):

- **Payment Infrastructure** — `XRP-USD`, `LTC-USD`, `BCH-USD`, `XLM-USD`
- **Web3 Infrastructure** — `ETH-USD`, `ADA-USD`, `ETC-USD`, `TRX-USD`, `EOS-USD`

Annualise these with `sqrt(365)` (crypto calendar).

Note in the log: `TRX-USD` is architecturally a smart-contract platform but
its dominant real-world usage is stablecoin/payment settlement — defensible
either way, state it as a judgement call rather than presenting the split as
objectively clean.

**Wiring these in:**

- Extend the recognised `FAMILIES` set (in `src/portfolios.py`, wherever
  `parse_fund_id`/`FAMILIES`/`METHODS` live) to include the 5 new family names
  (e.g. `defensive`, `cyclical`, `growth_sensitive`, `payments`, `web3infra` —
  pick clean, consistent snake_case ids). Fund ids follow the existing
  `{family}_{method}` pattern (e.g. `defensive_equal_weight`,
  `payments_risk_parity`) so `parse_fund_id` keeps working via `split("_", 1)`.
- These 10 new funds (5 groupings × 2 methods) get appended to the *same*
  `results/data/fund_returns.csv`, `results/data/fund_weights.csv`, and
  `results/tables/performance_metrics.csv` as the existing 12 — don't create
  parallel files. The required baseline 12 must remain intact and unchanged
  within those files.
- Add the same sanity assertions used for the original 12 (weights sum to ~1,
  no negatives, no look-ahead, methods differ from each other where more than
  one method exists for a family).
- Add each new grouping's growth-of-$1 to a new figure (or figures) in
  `results/figures/`, using the end-label style from part 2 below.
- Document the sector-cluster and crypto-theme membership, and the rationale,
  in `README.md`.

## 2. Growth-of-$1 figures: label the final value on the right, like Part A

My completed Part A folder's `scripts/run_part_a.py` has a
`_plot_growth_of_1` function (around line 224) that labels each line's final
value at the right edge (`$X.XX`, color-matched to its line, with
collision-avoidance nudging and a leader line when labels would overlap). Part
B's current growth-of-$1 figures (`growth_of_1_equity.png`,
`growth_of_1_crypto.png`, `growth_of_1_combined.png`) don't have this.

Read that Part A function directly and port the end-labelling logic into
Part B — either as a shared helper in `src/style.py` (preferred, since other
growth-of-$1-style figures will want it too: the fusion comparison, the new
grouping figures, and the vol-targeting comparison in part 3 below) or
adapted per-figure if a shared helper doesn't fit cleanly. Apply it to every
growth-of-$1-style figure Part B produces, existing and new. Don't touch the
already-fixed caption/period logic (`_period`/`_caption`) while doing this —
this is purely about the end-of-line value labels.

## 3. Volatility-targeting overlay (the extension we agreed on)

This is a genuine structured-side extension (cite Moreira & Muir 2017, as the
brief itself does for this idea), not a 13th-vs-14th fund variant — build it
as an overlay applied on top of an existing fund's return series, in a new
`src/vol_target.py`.

- **Target volatility**: use the base fund's own full-sample realised
  annualised volatility as the target (so the overlay smooths exposure toward
  the fund's natural average vol over time, rather than being an implicit
  always-de-risk bet). State this choice explicitly in the log/README.
- **Trailing realised vol**: 60-trading-day rolling standard deviation of the
  base fund's daily returns, annualised.
- **No look-ahead**: the scaling factor for day *t* uses only trailing vol
  computed from returns strictly before *t* — same `assert_no_lookahead`
  pattern already used elsewhere.
- **Scaling factor**: `k_t = target_vol / realised_vol_(t-1)`, clipped to a
  stated band — use `[0.5, 1.5]` unless you have a good reason to pick
  something else, and state whatever you land on. This keeps it a genuine
  "smoothing" overlay (partial de-risking in high-vol regimes, modest
  scale-up in calm regimes) without introducing real leverage/margin
  complexity into a long-only retail-facing product.
- **Scaled return**: `k_t * base_fund_return_t`.
- Apply this to **Combined Maximum-Sharpe** (required — it's the fund with the
  worst drawdown, −52.7%, so it's the clearest before/after story). If time
  allows, also apply it to one more fund of your choice for a broader
  comparison — optional, not required.

Produce:
- `results/tables/vol_target_comparison.csv` — base vs. vol-targeted:
  annualised return, vol, Sharpe, max drawdown (same shape as
  `fusion_comparison.csv`).
- A growth-of-$1 comparison figure (base vs. vol-targeted, with the same
  end-labelling from part 2).
- A second figure showing the scaling factor `k_t` over time, so the
  de-risking/scaling behaviour is visible on its own, not just inferred from
  the return comparison.

## After all three parts

- Run the full pipeline end to end, regenerate everything, and re-verify (as
  before — actual output, not just "the code should work now"): all 22 funds
  present and sane, growth-of-$1 figures show end labels, vol-target
  comparison numbers make sense (vol-targeted Sharpe/drawdown should generally
  look less extreme than the base Combined Max-Sharpe fund, though report
  honestly whatever the real numbers show).
- Extend `tests/test_smoke.py` with checks for the new funds (weights sum to
  1, no negatives, no look-ahead) and for the vol-targeting scaling factor
  (no look-ahead, stays within the stated clip band).
- Add a new entry to `ai/prompt_log.md` (same format as existing entries) for
  anything that went wrong or was a real judgement call while building this —
  particularly flag anything about the sector-cluster/crypto-theme membership
  or the vol-targeting design choices that took real thought, not just
  mechanical implementation.
- Update `README.md`'s design-decisions and output-file sections to cover the
  10 new funds and the vol-targeting outputs.

Report back: the new funds' Sharpe ratios (all 10), the vol-target comparison
numbers (base vs. targeted), confirmation the growth-of-$1 end labels are in
place, and anything that surprised you or required a judgement call.
