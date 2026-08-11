# Prompt 07 — Git init, commit, and push to a private GitHub repo

This folder (`z5710071_projectB`) has no git history yet. This prompt gets
it into a private GitHub repo, ready for the Streamlit Cloud connection step
— which needs my own login and isn't part of this prompt.

## 1. Check `.gitignore` before committing anything

Before running `git init`, verify `.gitignore` correctly excludes:
- Raw source data — any cached `.parquet` files or the downloaded data ZIP
  `src/data_access.py` caches locally (check where it actually caches to;
  make sure that path is ignored, or confirm it caches outside this folder
  entirely).
- Secrets, API keys, tokens — confirm none exist in the repo at all (grep
  for anything that looks like a key/token/credential before committing,
  not just trusting `.gitignore`).
- `__pycache__/`, `.venv/`, `.pytest_cache/`, and similar standard noise.

And confirm it does **NOT** exclude:
- `results/` — the precomputed data, tables, and figures the app reads and
  that markers need to see. These must be committed (the brief is explicit:
  "commit your code AND your precomputed app artifacts under results/").
- `src/lexicons/*.csv` (the Loughran-McDonald dictionary and the finVADER-lite
  extension) — these were deliberately un-ignored earlier in the build
  (check `ai/prompt_log.md` for that entry) since they're committed
  artifacts, not raw project data.
- `assets/*.png` (the Invesper logo and icon added in an earlier round) —
  check carefully whether any existing `.gitignore` rule for images (e.g. a
  blanket `*.png` line with a carve-out only for `results/figures/`) would
  silently catch these too. This is a real risk: the app would still run
  fine locally either way, so a missing logo wouldn't be obvious until the
  deployed version is missing it. Verify explicitly, don't assume.

More generally: after staging, look at the actual list of staged files
(`git status` / `git diff --cached --stat`) before committing, and sanity
check there's nothing unexpectedly large or unexpectedly missing — don't
just trust that `.gitignore` is doing the right thing by inspection alone.

Fix `.gitignore` first if anything's wrong, before the first commit — don't
commit something wrong and clean it up in a second commit.

## 2. `git init` and initial commit

- First, check whether any parent directory (e.g. `fins-agent`) is already
  its own git repository — from earlier context, it likely is, with
  unrelated course content in it. That's expected and fine (the brief
  states this folder is meant to be "its own repository, independent of
  fins-agent"), but be deliberate about it: run `git init` specifically at
  `z5710071_projectB`'s root (not the parent, not any subfolder), and make
  sure every git/gh command in this prompt is run with your working
  directory exactly there, so nothing accidentally interacts with or gets
  picked up by the parent repo.
- Stage everything that should be committed per step 1, and make one clean
  initial commit with a sensible message (e.g. summarising that this is the
  Part B submission: funds, sentiment, fusion, vol-targeting, and the
  Streamlit app).

## 3. Run `scripts/check_handin.py` for real — now that git history exists

Station 4 now exists, so this should actually be run properly (not skipped
like every earlier round). Run it **after** step 2's initial commit, not
before — its "no raw data or secrets committed" check needs real git
history to check against; running it against an uncommitted working
directory wouldn't actually validate anything.

Fix every `[FAIL]` it reports. `[WARN]`s are just reminders — use judgement
on whether they need action. If any fixes are needed, make a follow-up
commit with them **before** pushing in step 4 — the state that ends up on
GitHub should already be the corrected one, not require a second push to
fix.

## 4. Create a private GitHub repo and push

- Check whether GitHub auth is already set up on this machine (`gh auth
  status` if the `gh` CLI is available, or check existing git credentials).
- **If authenticated**: create a new **private** GitHub repository (pick a
  sensible name, e.g. matching the folder name) — use the explicit private
  option (`gh repo create --private ...` if using the CLI, or the private
  toggle if creating it via the GitHub UI). Do not let it default to public
  at any point, even briefly. Push the commit(s) to it.
- **If not authenticated**: stop here and tell me exactly what to run —
  either `gh auth login` if the GitHub CLI is installed, or the manual
  alternative (create an empty private repo on GitHub.com myself, then the
  exact `git remote add origin ...` / `git push` commands to run once it
  exists). Don't guess at credentials or try to work around missing auth.

**The repository must be private.** Do not make it public — that only
happens at hand-in, later, and it's a manual step I'll do myself.

## 5. Verify

- Confirm the push succeeded and the repo is actually private (check via
  `gh repo view` or the GitHub UI, don't just assume).
- Double-check nothing sensitive or raw made it into the pushed history —
  look at what actually got committed, not just what `.gitignore` claims to
  exclude.
- Confirm `results/` and `src/lexicons/*.csv` did make it in (check the repo
  contents, not just local `git status`).

## After

Add a new entry to `ai/prompt_log.md` covering this — what `.gitignore`
looked like before/after (if it needed fixing), any `check_handin.py`
failures found and fixed, and the repo situation (name, private status).

Report back: the repository name/URL, the default branch name (main or
master — I'll need this for the Streamlit Cloud connect step), confirmation
it's private, whether `check_handin.py` needed any fixes, and — if auth
wasn't already set up — exactly what I need to do to get it authenticated
so this can complete.

I'll handle the Streamlit Cloud connection step myself once this is done —
that doesn't need a prompt, just tell me the repo is ready.
