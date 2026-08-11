# Prompt 05 — Make the 4 extension variants fully interactive in the app

Right now the fusion tilt variants (`equity_min_variance_momentum`,
`equity_min_variance_contrarian`) and the vol-targeted variants
(`combined_max_sharpe_vol_targeted`, `crypto_max_sharpe_vol_targeted`) only
exist as summary rows in `fusion_comparison.csv`/`vol_target_comparison.csv`
— no daily return series was ever saved for them, so the app currently shows
an explicit "no published return history" note on their fact sheets instead
of real charts, and they're excluded from the allocation builder entirely.

This matters because these 4 variants **are** the sentiment-fusion and
volatility-targeting extensions — the actual innovation-band work — so right
now they're the only funds a user can't fully interact with in the app.
Fix this properly rather than leaving the note in place.

## 1. Append the 4 variants' daily return series to `fund_returns.csv`

The return series already exists in memory during the pipeline — it just
isn't being written out:
- Fusion: `weights_to_daily_returns` (or whatever function currently produces
  the momentum/contrarian daily returns in `src/fusion.py`) already computes
  this for both tilts.
- Vol-target: `apply_overlay`'s `scaled` return series in `src/vol_target.py`
  already computes this for both funds.

In `scripts/run_part_b.py`, after building the fusion and vol-target results,
append their daily return series to the same long-format `fund_returns.csv`
table (columns: date, fund, return) under the ids above — not a separate
file. This is the only change needed for the app's growth-of-$1 and
drawdown charts to work for these funds automatically, since both are
already driven by `fund_returns.csv`.

## 2. Handle "current holdings" for each variant correctly

These two variant types are structurally different, so handle them
differently — don't force both into the same treatment:

- **Fusion variants** (momentum/contrarian) genuinely reallocate weights
  across assets — that's the whole mechanism. Check whether `src/fusion.py`
  already has the tilted weight series available (it needs weights to
  compute the returns, so it likely does even if not currently persisted).
  Append these to `fund_weights.csv` in the same schema as every other fund.
  If the tilt is computed at a different granularity than the monthly
  rebalance dates used elsewhere (e.g. a daily-updating tilt on top of
  monthly base weights), use the most recent available date's weights as
  "current holdings" for the fact sheet — same UI behaviour as every other
  fund, just sourced from whatever the tilt's actual granularity is.
- **Vol-targeted variants** don't reallocate across assets at all — the
  overlay is a portfolio-level scalar (`k_t`) applied to the whole fund's
  return, not a per-asset reweighting. So their "current holdings" are
  identical to their base fund's holdings (`combined_max_sharpe` /
  `crypto_max_sharpe`). Don't duplicate rows in `fund_weights.csv` for
  these two — instead, have the app's fact-sheet logic fall back to the base
  fund's weights when a vol-targeted variant is selected, with a short
  caption explaining why: "Volatility targeting scales overall exposure, not
  individual holdings — shown here are the underlying [base fund name]'s
  holdings."

## 3. Update the app

- Remove the "no published return history" special-case note — these 4 now
  have real data, so their fact sheets should render exactly like every
  other fund's (growth, drawdown, 4 metrics, holdings), with the vol-target
  holdings caption from part 2 where applicable.
- Add all 4 to the allocation builder's fund picker, in whichever universe
  they belong to (fusion variants → Equity, vol-target variants → their base
  fund's universe, same as how they're already categorised elsewhere in the
  app).

## 4. Gauge caption fix

The market-wide sentiment gauge currently uses `sentiment_aligned` (the
unlagged value) rather than the lagged `sentiment` column used everywhere
else. That's fine for a pure display gauge (it's informational, not feeding
any trading decision, so there's no look-ahead concern), but it needs to say
so explicitly — add a short caption near the gauge: something like "Current
reading (unlagged) — for display only; fund construction uses the lagged
signal shown in the sector chart." Don't change which column the gauge
uses, just make the distinction visible to whoever's looking at it.

## 5. Tests and verification

- Update `tests/test_app_data.py` / `tests/test_app.py` to cover the 4
  variants having real charts now (replace whatever tested the old
  "no published history" note), and to cover them being selectable in the
  allocation builder.
- Check whether any Station 3 test in `tests/test_smoke.py` asserts an exact
  fund-id set or row count on `fund_returns.csv`/`fund_weights.csv` — if so,
  update it to account for the 4 new rows appended, rather than letting it
  either silently pass on stale expectations or fail.
- Re-run the full pipeline, `streamlit run streamlit_app.py` locally to
  confirm all 4 variants now show real fact sheets and appear in the
  allocation picker, then the full test suite and ruff.

## After

Add a new entry to `ai/prompt_log.md` (existing format) covering this — it's
a legitimate design correction (the variants being fully usable products
now, not just summary statistics) worth recording properly, not a minor
tweak. Update `README.md` if the output-file descriptions need adjusting
(fund_returns.csv / fund_weights.csv now include the variant rows).

Report back: confirm all 4 variants now have working fact sheets and are
selectable in the allocation builder, how the fusion-variant weights
granularity turned out to work, and confirm the gauge caption is in place.
