# Prompt 09 — Fix six figure issues, then swap them into report.docx surgically

## Absolute rule — read this before doing anything else

**`report/report.docx` has already been manually edited (text and
formatting) and this must be fully preserved.** Do not run
`scripts/build_report.py` or any script that regenerates the document from
scratch — that would blow away the manual edits. But the actual figures
inside it **do** need updating once fixed, so this prompt ends with a
surgical, text-safe swap, not a manual "go do this in Word yourself" step.

Here's how to do that safely: a `.docx` file is a zip archive. The text and
formatting live in one XML part inside it (`word/document.xml`); each
embedded image is a separate binary file inside the same archive
(`word/media/image1.png`, `image2.png`, etc.), completely independent of the
text part. This means you can replace just the image bytes inside the
archive — swapping `word/media/imageN.png`'s contents for the corresponding
regenerated figure — **without opening, parsing, or touching
`word/document.xml` or any other part of the document at all.** Don't use
`python-docx` to "re-insert" images (that touches the document structure);
work directly with the zip archive's image parts instead.

Steps for the swap, once the six figure fixes below are done and the new
PNGs exist in `results/figures/`:

1. **Back up first**: copy `report/report.docx` to
   `report/report_backup_before_figure_swap.docx` before changing anything,
   as a safety net.
2. **Build an accurate mapping** from each embedded image in the docx to the
   correct regenerated figure — use `scripts/build_report.py` (or whatever
   originally inserted the figures) to see the actual insertion order/source
   file for each one. Don't guess based on image numbering alone.
3. **Swap only the image bytes** for whichever embedded images correspond to
   the six figures that changed — leave every other embedded image and all
   document text/formatting completely untouched.
4. **Verify the swap was truly surgical**: after swapping, confirm
   `word/document.xml` (and every other non-image part of the archive) is
   byte-identical to what it was before — this proves the text/formatting
   wasn't touched, not just assumed.

One figure needs special handling: the **Sharpe barplot** is changing shape
significantly (short/wide → tall/horizontal, per item 3 below). Don't try to
also resize its display frame in the document to compensate — just swap the
image itself like all the others, and leave the frame as-is even if that
means the new image looks stretched or squished in its old frame. Note this
clearly in the report-back so the student knows to manually resize just that
one image's frame in Word afterward (drag a corner handle) if it looks off —
that's a quick manual fix, much lower-risk than an automated frame resize
would be.

## Context

Read `ai/prompt_log.md` in full first. All six issues below were found by
directly inspecting the actual current figures, not from a description —
verify each one yourself against the real PNGs before fixing, and verify
again after regenerating.

## 1. Chart axis date formatting (project-wide)

Most figures currently show raw `2021-01`-style axis tick labels. Fix this
in the shared plotting logic (`src/style.py` / `src/plots.py`, wherever the
date axes are configured) so it applies consistently across every
time-series figure, not per-chart. Use a cleaner format — "Jan 2021" style
for charts with many ticks across a multi-year span (which is most of
them), or the fuller "January 2021" if a specific chart has few enough ticks
that the full form fits comfortably without crowding. Use judgement per
chart's actual tick density rather than one hardcoded rule everywhere.

Apply this to every figure with a date axis, at minimum: `growth_of_1_equity`,
`growth_of_1_crypto`, `growth_of_1_combined`, `growth_of_1_sector_clusters`,
`growth_of_1_crypto_themes`, `drawdown_combined_max_sharpe`,
`fusion_growth_comparison`, `growth_vol_target_combined_max_sharpe`,
`growth_vol_target_crypto_max_sharpe`, `vol_target_scaling_combined_max_sharpe`,
`vol_target_scaling_crypto_max_sharpe`, `sector_sentiment_index`,
`sentiment_lexicon_comparison`, `portfolio_weights_combined_min_variance`.
Check for any other figure with a date axis you find along the way too.

## 2. Legend overlapping plotted lines

Confirmed on `growth_of_1_crypto.png` and `growth_of_1_combined.png` — the
legend is placed in a fixed position that overlaps the actual data. Fix by
switching to automatic best-placement (e.g. matplotlib's `loc='best'`, which
picks whichever corner has the least overlap with plotted artists) rather
than a hardcoded position, so it adapts per chart instead of needing manual
tuning. Apply this to every multi-line growth-style chart, and check the
others (`growth_of_1_equity`, `growth_of_1_sector_clusters`,
`growth_of_1_crypto_themes`, `fusion_growth_comparison`, the two
`growth_vol_target_*` charts) for the same latent issue even if it wasn't
called out explicitly — verify each one visually after the fix, don't just
assume `loc='best'` solved it everywhere without checking.

## 3. Static Sharpe barplot — rebuild horizontal

`results/figures/sharpe_barplot.png` (all 22 funds) currently has rotated,
overlapping x-axis fund-name labels, and its legend also overlaps the last
two bars (the Web3 Infrastructure funds). The app's own dynamic version of
this chart was already fixed to a horizontal layout in an earlier round —
find that fix (check `streamlit_app.py` / `app/data.py` for how it built
its horizontal Sharpe chart) and apply the same approach to this static
figure: Sharpe ratio on the x-axis, fund display names on the y-axis, sorted
by Sharpe descending. With 22 categories this will need a taller figure —
size it so every label has room, and fix the legend placement (per item 2's
approach) so it doesn't overlap any bar.

## 4. Sentiment lexicon comparison — right subplot date overlap

In `sentiment_lexicon_comparison.png`, the right-hand "Monthly mean headline
sentiment" subplot has overlapping, unreadable x-axis date labels — it's
narrower than the full-width charts, so item 1's format fix alone may not
be enough. After applying the date-format fix, check this subplot
specifically; if labels still crowd, reduce tick density (e.g. every 6
months or yearly instead of every tick) and/or rotate the labels, whichever
reads more cleanly, then verify visually.

## 5. Volatility-targeting scaling-factor charts — verify then fix line visibility

In `vol_target_scaling_combined_max_sharpe.png` (and check the crypto
version too), the `k_t` line appears to disappear for an extended stretch,
looking like blank space. **First verify this is real** — check the actual
`k_t` values for that date range directly (in whatever holds the daily
scaling-factor series) to confirm they're genuine values sitting at the 1.5
clip bound, not `NaN`/missing. This matters because the pinned-at-ceiling
period is itself part of the report's actual finding (the overlay staying
over-levered through a calm stretch before the 2022 crash) — it should stay
visible as real data, not be hidden or cropped away.

If it's real data, the likely cause is the `k_t` line visually coinciding
with the thin dashed reference line marking the clip ceiling, making a solid
line and a dashed line at the same height blend together. Fix by making the
actual `k_t` series bold/solid and drawn with a higher z-order than the
reference line, so it's clearly visible as real, continuous data even when
pinned at the bound. As a nice addition if it's easy: lightly shade the
periods where `k_t` sits exactly at a clip bound (0.5 or 1.5), which
visually reinforces exactly when the constraint is binding.

If it turns out to actually be missing/NaN data rather than a rendering
overlap, that's a different, real bug in the vol-targeting code — fix the
actual cause, don't paper over it with a styling change.

## 6. Vol-target scaling charts — caption stretching the whole canvas

Both `vol_target_scaling_*.png` files have an unusually long single-line
caption (a fuller methodology sentence than most other captions), and
because `save_fig` uses `bbox_inches="tight"`, the entire canvas expands to
fit that one long unwrapped line — leaving a large blank stretch to the
right of the actual chart, since the chart itself stays normal width while
the canvas grows to fit the caption. Fix by wrapping the caption text to a
fixed width (roughly matching the chart's own width) in the shared caption
helper, so this can't happen regardless of how long any given caption is.
Check other figures with longer-than-usual captions for the same latent
issue while you're in there.

## After all six fixes

- Regenerate the figures via the normal pipeline (`scripts/run_part_b.py`)
  — this only touches `results/figures/`.
- Visually verify each of the six fixes directly in the regenerated PNGs —
  actual rendered dates, actual legend position relative to the data, actual
  bar orientation, actual subplot tick readability, actual `k_t` line
  visibility, actual canvas width — not just "the code ran without error."
- Then do the surgical docx image swap described above: back up, map old
  images to new figures accurately, swap only the changed ones' bytes,
  verify `word/document.xml` is unchanged.
- Run the test suite and ruff.
- Add a new entry to `ai/prompt_log.md` (existing format).

Report back: confirmation all six figure fixes are actually correct (with
what you saw when checking, not just what the code should do), confirmation
the docx swap is verified surgical (text/formatting byte-identical before
and after), which images were swapped, and the note about the Sharpe
barplot possibly needing a manual frame resize in Word.
