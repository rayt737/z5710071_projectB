# Prompt 08 — Write the Part B report

Everything the report needs to describe is now built and verified: 26 funds
across three universes, the walk-forward backtest, the sentiment index and
lexicon extension, the fusion tilt, the volatility-targeting overlay
(including the look-ahead bug that was caught and fixed), and the deployed
Streamlit app. This prompt drafts the actual report.

## Read first

- `ai/prompt_log.md` in full (all entries — this is the real history of what
  was built, what broke, and what was decided; the report's narrative should
  be consistent with it, not a cleaner invented version of events).
- `PROJECT_BRIEF.md` Section 5 (Part B's report requirements) and the
  marking rubric.
- `README.md` for the current, accurate description of every output file
  and design decision.
- My completed Part A folder's `report/report.docx` (or the underlying
  generation script if one exists, e.g. `scripts/build_report.py`) — this is
  the reference for tone, structure conventions, the `[REVIEW]` tag pattern,
  equation formatting, and reference-list style. Follow its conventions
  where they make sense for Part B; Part B's own actual content and the
  brief's actual Part B requirements take precedence wherever they differ
  from Part A's specifics.
- Part B's own `report/OUTLINE.md` (a planning stub — use or discard as
  useful).

## Length and format — clarified by the professor beyond what's in the brief

- **Exhibits go inline in the body, not in an appendix** — this matches Part
  A's actual report exactly (checked directly: it contains zero appendix
  references anywhere). Every table/figure is placed directly above the
  paragraph that discusses and interprets it, right in the flow of the
  section it belongs to — not collected at the end. The brief's "exhibits
  may go in an appendix" line is an option, not a requirement, and it's not
  the option being used here.
- **10 pages is still a text-only limit** — inline exhibits don't count
  against the 10 pages of narrative text (per the professor's clarification
  that the page limit is text-only), even though they're placed in the body
  rather than a separate section. Keep the actual prose focused and let the
  exhibits carry the detail, the same way Part A's report does.
- **~5,000 words, with up to 5% leeway if genuinely needed** (~5,250 words
  max) — don't treat 5,000 as a hard wall, but don't use the leeway as an
  excuse to pad either.
- Author the editable source at `report/report.docx`, submit as
  `report/report.pdf`.
- **Audience and tone**: write for a financially literate but non-technical
  reader, same as Part A's convention — enough technical detail that the
  methodology could be reproduced, but every exhibit interpreted in plain
  English, not left as a wall of statistics. This is also a stated course
  learning outcome (communicating data-driven analysis clearly to a
  non-technical client), not just a style preference.
- If anything about formatting conventions is genuinely unclear or Part A's
  approach doesn't obviously carry over to Part B's content, make a
  reasonable judgement call and flag it clearly (a `[REVIEW: ...]` note is
  fine) rather than guessing silently — this gets fixed in the edit pass
  either way.

## Non-negotiable rules

- **Every number in the prose must come from the same computed object as
  the tables/figures it accompanies** — never hardcode or retype a number by
  hand. Pull live from the actual current CSVs under `results/` at the time
  of writing, not from memory of what any number was at an earlier point in
  this build (several numbers changed slightly across the fixes in this
  project's history — e.g. the vol-targeting numbers changed materially
  after the look-ahead bug fix — so anything written down anywhere earlier
  in this project's history should be treated as potentially stale; the
  CSVs are the only source of truth).
- **Tag every genuinely interpretive claim with `[REVIEW]`** — anything that
  states *why* a result happened, any economic judgement, any
  recommendation, any claim about what a result "means" for an investor.
  Purely descriptive statements of fact drawn directly from a table/figure
  (e.g. "the equity equal-weight fund's out-of-sample Sharpe ratio was
  X.XX") don't need the tag; anything interpretive does. This mirrors Part
  A's convention and exists so the student's edit pass has a clear map of
  what needs their own judgement, not just their own rewording.
- **Thesis-style equation formatting, applied consistently to every formula
  in the document** (backtest return, Sharpe ratio, the sentiment tilt
  formula, the volatility-targeting scaling factor, any others used):
  centered on its own line, space above and below, a sequential reference
  number in parentheses flush against the right margin, every variable
  defined immediately after the equation. Not just the first equation — all
  of them, consistently.
- **Don't fabricate citations.** Use the same reference list Part A/the
  Week 10 deck already established (Baker & Wurgler 2007, DeMiguel, Garlappi
  & Uppal 2009, Hutto & Gilbert 2014, Maillard, Roncalli & Teiletche 2010,
  Markowitz 1952, Moreira & Muir 2017, Sharpe 1966, Tetlock 2007) — cite
  whichever of these are actually relevant to what's being discussed, in the
  same author-year in-text style, with a matching References section.
- **This report gets hand-edited in Word after this draft.** State this
  explicitly in whatever notes/log you leave: once `report/report.docx`
  exists and has been opened/edited, any future automated regeneration must
  make surgical edits only — never blow away manual edits by re-running a
  generation script wholesale. This is a standing rule for every future
  report-related prompt, not just this one.
- **Refer to funds by their investor-facing display names** (from
  `results/data/fund_display_names.csv` / `src/branding.py`), not raw
  technical fund ids, anywhere the report discusses a specific fund by name
  — e.g. "the Invesper US Equity Opportunities Fund," not
  "equity_max_sharpe." This keeps the report consistent with what a reader
  would actually see if they opened the app. Technical ids are fine in
  exhibit tables themselves if that's how the underlying CSVs are
  structured, but prose should use the real names.
- **Do not commit or push this draft.** Leave it in the working tree for
  review. The report gets committed once it's actually been through the
  student's edit pass, not as an AI-generated first draft — that's a
  separate, later step.

## The six required sections (per the brief's suggested structure)

**1. The funds and the backtest design.** All 26 funds (walk through the
scope: the required-minimum 12 core funds across equity/crypto/combined ×
four methods, the 5 additional groupings — 3 equity sector-clusters, 2
crypto themes — built with equal-weight and risk parity only since no
market-cap data exists, and why that scope choice was made). The
walk-forward methodology: expanding window, monthly rebalance, the actual
first live dates as derived from the real data (pull these from the CSVs,
don't assume), rf = 0, the equity/combined vs. crypto annualisation split
and why. State every design choice as a stated assumption, not an implied
default — **including that the backtests assume zero transaction costs**
(explicitly permitted by the brief when stated). Note briefly here that this
choice is revisited as a deliberate pricing decision in Section 5 (Invesper's
zero-commission model), not just a modelling simplification — the two are
connected and the report should say so, rather than presenting them as
unrelated facts in two different sections.

**2. Out-of-sample results and fund fact sheets.** The performance-metrics
table across all funds, discussion of what the results actually show —
including the genuinely interesting finding that equal-weight beats every
optimised equity fund out-of-sample (this is real, verified, and matches
both DeMiguel et al. 2009's own finding and the Week 10 deck's own reference
run — a strong, legitimate point, not something to downplay). Discuss growth
of $1, drawdown, and weights-over-time figures with real interpretation, not
just description.

**3. The sentiment index.** VADER as the baseline, the finVADER-lite finance
lexicon extension (grounded in the Loughran-McDonald dictionary, two-pass
rated with agreement filtering — the actual methodology and its honest
limitations, e.g. headlines-only as a noisy proxy, the no-news-day
carry-forward choice and why). The sector sentiment index construction and
what it shows. State plainly that sentiment work applies to the equity data
only — crypto is price-only in this project, with no news/sentiment
dimension, consistent with the brief.

Include the plain-VADER-vs-finVADER-lite comparison
(`results/figures/sentiment_lexicon_comparison.png` — precomputed, still
exists even though it's no longer shown in the app) inline in this section,
directly above the paragraph discussing it. This is now the *only* place
this evidence appears anywhere in the submission, and it's the direct
evidence that the lexicon extension actually did something measurable —
don't let it go missing just because it was dropped from the app for UI
reasons.

**4. Extensions and innovations.** This section carries real weight (30% of
Part B is the Innovation band) — cover the sentiment fusion tilt (the
honest, untuned before/after comparison, and the turnover-cost story: the
tilt's edge before costs vs. its turnover spike) and the volatility-targeting
overlay **including the look-ahead bug and its fix** as a genuine, valuable
finding, not something to hide — explain what the original (flawed) target
was, why it was look-ahead bias, what the corrected target is, and what the
corrected, honest result actually shows (report whatever the current real
numbers say — pull them fresh from `results/tables/vol_target_comparison.csv`,
don't rely on any number quoted earlier in this project's history). A
well-explained methodology mistake that got caught and fixed is exactly the
kind of AI-workflow and analytical rigor this section can legitimately
showcase — don't sanitise it into just "we tried volatility targeting."

**5. The app and the investor journey.** Describe the actual deployed app as
it exists now: the three universe groupings (Equity/Crypto/Multi-Asset), the
five sections (Compare, Fact Sheet, Sentiment analytics, Allocation builder,
Portfolio), the per-fund management-fee schedule and the blended-fee
calculation, the zero-commission pricing framing (and why — mirroring the
real 2019+ zero-commission brokerage/robo-advisor model), and the Portfolio
tab's session-only persistence (state this limitation honestly, same as the
app itself does). Describe the actual investor journey a user would follow,
not an aspirational one.

If screenshots of the running app are easy to capture (e.g. via a
lightweight local automated screenshot of `streamlit run`, if that's
readily available in this environment), include a few inline in this
section, directly alongside the part of the journey they illustrate — but
don't let this block the report if it's not straightforward; a clear
written description is the minimum requirement.

**6. Critical reflection and three concrete recommendations.** This needs to
be genuinely evidence-based, not generic. Real material already exists to
draw from — for example: what the equal-weight-dominance finding implies
about the value of complexity in a real product; what the vol-targeting
overlay's sensitivity to its calibration window implies about deploying this
kind of technique in practice (the 2020 window happening to include the
COVID crash meaningfully changed the result); what the fusion tilt's
turnover-cost problem implies about whether a real fund would ever run it
as-is. Use real findings like these as a starting point, but the actual
three recommendations should be `[REVIEW]`-tagged and specific, not
templated advice.

## Exhibits

Include the required 7 exhibits at minimum (performance-metrics table,
growth-of-$1, drawdown, weights-over-time, Sharpe barplot, sentiment-index
time series, fusion before-vs-after) — pull these from `results/figures/`
and `results/tables/` directly, don't regenerate them. Given how much
additional work exists beyond the minimum (the 5 new groupings, the
volatility-targeting figures), include the extra ones too — all placed
inline, in the relevant section, matching Part A's convention. If the
narrative is at risk of running long because of this, trim prose rather than
moving exhibits out of the body — the exhibits themselves don't count
against the 10-page text limit, so they're not what needs cutting. Every
exhibit gets a caption (source, sample period, units) and is referenced and
interpreted from the paragraph immediately following it — never dropped in
uninterpreted.

## After drafting

- Generate `report/report.pdf` from `report/report.docx` if a conversion
  path is available in this environment (e.g. Word itself, or a library like
  `docx2pdf`) — if nothing reliable is available, say so clearly and note
  that the student will need to export it from Word manually.
- Count the actual narrative word count (excluding exhibit captions and the
  reference list) and confirm it's within the
  ~5,000-5,250 word range — if it's over, trim rather than leave it
  over-length.
- Spot-check at least five numbers quoted in the prose directly against
  their source CSVs to confirm traceability before reporting back.
- **Add a new entry to `ai/prompt_log.md`** (existing format, same as every
  other entry in this project) covering this report-writing pass — what was
  drafted, any real judgement calls made while writing (e.g. anything that
  needed genuine interpretation rather than mechanical description, any
  place Part A's conventions didn't cleanly carry over), and note explicitly
  that this is a draft awaiting the student's review, not a final submitted
  version. This is a real, substantial piece of work — log it properly, the
  same as every build step before it.

Report back: the actual word count, section-by-section confirmation of
what's covered, how many `[REVIEW]` tags were left and roughly where they
cluster (so the student knows where to focus their edit pass), whether PDF
generation worked, and confirm nothing was committed to git.
