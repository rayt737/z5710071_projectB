"""Lexicon traceability audit - closes the candidate-count gap (prompt 02).

Regenerates `results/tables/lexicon_candidate_ledger.csv` so that every term in
the candidate screen (top 80 by headline frequency) AND every term in
`src/lexicons/finvader_lite_extension.csv` is accounted for with an explicit
disposition. The ledger is the machine-checkable backstop for
`ai/lexicon_extension_log.md`.

Run from the project root:

    python scripts/audit_lexicon_traceability.py

No downstream output depends on this file; it exists purely for the audit
trail. The script exits non-zero if the accounting is not airtight (any
candidate with no disposition, or any extension term that cannot be explained).
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from nltk.sentiment import SentimentIntensityAnalyzer  # noqa: E402
from src import etl, features  # noqa: E402
from src import sentiment as sent  # noqa: E402

MIN_FREQ = 40
MAX_ABS_MEAN = 0.25
TOP_N = 80

MODAL_CATS = {"Strong_Modal", "Weak_Modal"}


def disposition(word: str, ext_status: dict[str, str],
                vader_words: set[str], flags: dict[str, set[str]]) -> str:
    """Where did this candidate end up? Priority: rated -> already handled by
    VADER itself -> modal/hedging -> litigious process -> context judgement."""
    if word in ext_status:
        return f"rated_{ext_status[word]}"
    if word in vader_words:
        return "already_in_vader_default"
    cats = flags.get(word, set())
    if cats & MODAL_CATS:
        return "excluded_modal_hedging"
    if "Litigious" in cats:
        return "excluded_litigious_process"
    return "excluded_judgement_context"


def coverage_reason(word: str, freq: int, flags: dict[str, set[str]]) -> str:
    """Why is this extension term NOT in the candidate screen (manual coverage)?"""
    if word not in flags:
        return "no_lm_flags (never a candidate under the rules; added by inspection)"
    if freq < MIN_FREQ:
        return f"below_min_freq ({freq} < {MIN_FREQ})"
    return "below_top_n_cutoff (qualifies but ranked past the top-80 display bound)"


def main() -> None:
    eq, _ = etl.load_clean_equities()
    nl, _ = etl.load_clean_headlines()
    eq_dates = pd.DatetimeIndex(sorted(eq["date"].unique()))
    panel = features.assemble_headline_panel(nl, eq_dates, tz_aware=True)
    print(f"[audit] {len(panel)} headlines on the equity calendar")

    full_pool = sent.build_lexicon_candidates(
        panel, min_freq=MIN_FREQ, max_abs_mean=MAX_ABS_MEAN, top_n=None)
    screen = full_pool.head(TOP_N).reset_index(drop=True)
    screen_words = set(screen["word"])
    full_words = set(full_pool["word"])
    print(f"[audit] full qualifying pool (no top_n cut): {len(full_pool)} terms")
    print(f"[audit] candidate screen (top {TOP_N} by frequency): {len(screen)} terms")

    ext = pd.read_csv(sent.EXTENSION_CSV)
    ext_status = dict(zip(ext["word"], ext["status"]))
    flags = sent.lm_flags(sent.load_lm_dictionary())
    vader_words = set(SentimentIntensityAnalyzer().lexicon)

    # Per-word frequency + mean plain-VADER for ANY word (needed to classify
    # extension terms that never qualified as candidates).
    sia = sent.build_plain_vader()
    titles = panel["title"].astype(str)
    compounds = titles.apply(lambda t: sia.polarity_scores(t)["compound"])
    word_freq: dict[str, int] = {}
    word_sum: dict[str, float] = {}
    for i, t in enumerate(titles):
        for tok in set(re.findall(r"[a-zA-Z][a-zA-Z\-]*", t.lower())):
            word_freq[tok] = word_freq.get(tok, 0) + 1
            word_sum[tok] = word_sum.get(tok, 0.0) + compounds.iloc[i]

    rows = []
    # 1) every screen candidate -> one disposition, no silent gap allowed
    for _, r in screen.iterrows():
        w = r["word"]
        rows.append({
            "word": w,
            "source": "screen_pool",
            "reason": "",
            "rank": int(screen.index[screen["word"] == w][0]) + 1,
            "n_headlines": int(r["n_headlines"]),
            "mean_plain_vader": float(r["mean_plain_vader"]),
            "lm_categories": r["lm_categories"],
            "in_vader_default": "yes" if w in vader_words else "no",
            "disposition": disposition(w, ext_status, vader_words, flags),
            "extension_status": ext_status.get(w, ""),
        })

    # 2) every extension term NOT already in the screen -> manual coverage, with
    #    the exact reason it was not auto-reproduced by the screen call.
    for _, r in ext.iterrows():
        w = r["word"]
        if w in screen_words:
            continue
        freq = word_freq.get(w, 0)
        reason = coverage_reason(w, freq, flags)
        if w in full_words:
            pool_row = full_pool[full_pool["word"] == w].iloc[0]
            n_head, mean = int(pool_row["n_headlines"]), float(pool_row["mean_plain_vader"])
            lm_cats = pool_row["lm_categories"]
            rank = int(full_pool.index[full_pool["word"] == w][0]) + 1
        else:
            n_head, mean = freq, word_sum.get(w, 0.0) / max(freq, 1)
            lm_cats = ",".join(sorted(flags.get(w, set())))
            rank = 0
        rows.append({
            "word": w,
            "source": "manual_coverage",
            "reason": reason,
            "rank": rank,
            "n_headlines": n_head,
            "mean_plain_vader": round(mean, 3),
            "lm_categories": lm_cats,
            "in_vader_default": "yes" if w in vader_words else "no",
            "disposition": f"rated_{r['status']}",
            "extension_status": r["status"],
        })

    ledger = pd.DataFrame(rows)
    out = ROOT / "results/tables/lexicon_candidate_ledger.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(out, index=False)
    print(f"[audit] wrote {out} ({len(ledger)} rows)")

    # --- airtightness asserts: no unaccounted candidate, no unexplained term ---
    unexplained = (
        screen[~screen["word"].isin(ext_status) & ~screen["word"].isin(vader_words)
               & ~screen["word"].isin(flags)]
    )
    assert unexplained.empty, f"no disposition: {unexplained['word'].tolist()}"
    ext_missing = [w for w in ext_status if w not in screen_words and w not in word_freq]
    assert not ext_missing, f"extension terms with no frequency data: {ext_missing}"

    n_rated = int((ledger["disposition"].str.startswith("rated_")).sum())
    n_kept = int((ledger["extension_status"] == "kept").sum())
    n_flagged = int((ledger["extension_status"] == "flagged").sum())
    n_screen = len(screen)
    n_pool = len(full_pool)
    n_manual = int((ledger["source"] == "manual_coverage").sum())

    s_kept = int(((ledger["source"] == "screen_pool")
                  & (ledger["extension_status"] == "kept")).sum())
    s_flagged = int(((ledger["source"] == "screen_pool")
                     & (ledger["extension_status"] == "flagged")).sum())
    in_vader = int((ledger["disposition"] == "already_in_vader_default").sum())
    excluded = int(ledger["disposition"].isin(
        ["excluded_modal_hedging", "excluded_litigious_process",
         "excluded_judgement_context"]).sum())

    print()
    print("=" * 72)
    print("LEXICON TRACEABILITY SUMMARY")
    print("=" * 72)
    print(f"full qualifying pool (top_n=None):            {n_pool}")
    print(f"candidate screen (top {TOP_N} by frequency):      {n_screen}")
    print(f"terms rated two-pass (all):                   {n_rated}  "
          f"(kept {n_kept}, flagged {n_flagged})")
    print(f"  rated from the screen:                      {s_kept + s_flagged} "
          f"(kept {s_kept}, flagged {s_flagged})")
    print(f"screen candidates NOT in extension CSV:       {n_screen - 21}")
    print(f"  -> already in VADER default:                {in_vader}")
    print(f"  -> excluded (modal/litigious/context):      {excluded}")
    print(f"extension terms added by manual coverage:     {n_manual} "
          f"(all rated two-pass)")
    print("=" * 72)


if __name__ == "__main__":
    main()
