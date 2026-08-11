# Prompt 10 — Final mechanical checks, checklist, and push

This is the last automated pass before the project goes to final human
review. Work efficiently — this is genuinely time-constrained (deadline
Friday) — but don't skip verification steps to save time; a missed real
issue costs more time than a careful check does.

## 1. Add the live links

Add a short "Live App" section near the top of `README.md` with the public
GitHub repo URL (`https://github.com/rayt737/z5710071_projectB`) and the
live Streamlit URL (`https://z5710071projectb.streamlit.app/`). Add the same
two links to `AGENTS.md` and `CLAUDE.md`. Keep it brief. Confirm both links
are actually correct before finishing.

(One combined `ai/prompt_log.md` entry covers this whole prompt — see
"After" at the end. Don't create a separate entry just for this step.)

## 2. Go through `SUBMISSION_CHECKLIST.md` explicitly, item by item

Don't just re-run `check_handin.py` and assume that covers it — go through
every line in `SUBMISSION_CHECKLIST.md` individually and verify each one for
real, ticking `[x]` only when actually confirmed. **If any item can't be
honestly ticked, fix the underlying issue first — don't tick it
prematurely, and note in the report-back what was found and fixed.**

- Folder is named `z5710071_projectB`.
- `report/report.pdf` is present, authored in Word/exported to PDF, and
  within limits — check both the actual page count (~10 pages of narrative)
  and the word count (~5,000 words, up to 5% leeway) fresh, since the
  student's own manual edits since the last check could have shifted either.
- The report includes every required exhibit from `PROJECT_BRIEF.md`
  Section 5 ("Required exhibits (Part B)") — check each one is present,
  **captioned, and interpreted** (referenced and discussed in the
  surrounding text), matching the checklist's actual wording — not just that
  the figure files exist on disk.
- At least the required combined fund with two methods, backtested
  out-of-sample with no look-ahead, with a fact sheet — this has been true
  for a long time, just confirm it's still intact.
- `streamlit_app.py` runs locally — actually run it, don't assume.
- The GitHub repo is public and the live Streamlit app loads — check the
  repo's actual visibility via the GitHub API (don't just trust it was set
  public earlier), and confirm the live URL responds.
- Raw data loads through `src/data_access.py`; no raw data or secrets
  committed — re-verify this is still true given everything committed since
  the last check.
- `AGENTS.md`/`CLAUDE.md` is the real, current version, not the stub.
- `ai/` contains the prompt logs and AI notes, and — while you're in
  there — confirm every prompt file (`prompt_01.md` through `prompt_09.md`,
  now living in `ai/prompts/`) is actually present and none are missing.
- **"The writing and interpretation are your own"** — the student has
  already personally confirmed this directly to me. Tick this item as
  confirmed; this is not something for you to independently verify or
  second-guess, just record it as done.
- **"Submit: the zip to Moodle, the public repo link, and the live Streamlit
  URL"** — leave this unticked. That's the student's own final action,
  hasn't happened yet, and isn't something for you to attempt (don't zip the
  folder or try to "complete" this step yourself).

Report back the full checklist with each item's actual status, not just
"all done."

## 3. Commit and push everything

- `git status` to see what's actually pending.
- Delete any `__pycache__`/`.pytest_cache`/`.ruff_cache` directories now
  rather than leaving `check_handin.py`'s reminder for later — cheap to do
  now, one less thing to remember at actual zip time.
- Run `scripts/check_handin.py` one final time — fix anything it flags
  before committing.
- Commit (clear message) and push to `origin master`.
- Verify against the actual GitHub remote (API or `git ls-remote`), not just
  local state, that everything landed correctly.

## After

Add **one** entry to `ai/prompt_log.md` covering this whole prompt (links,
checklist verification, any fixes made, the push) — not a separate entry per
step.

Report back a clear summary: the completed checklist (item by item, noting
anything that had to be fixed to earn its tick), confirmation everything is
pushed and verified on the remote, and explicitly state that the project is
now ready for final review before submission.
