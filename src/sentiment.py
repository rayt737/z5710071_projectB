"""Station 3 - sentiment model: VADER + a finance lexicon extension, and the
sector sentiment index.

Design (see ai/lexicon_extension_log.md for the full, graded trail):
1. Base: score every headline with plain VADER on the RAW text (no lowercasing,
   no punctuation stripping - VADER needs caps, punctuation and negation cues).
2. Extension ("finVADER-lite"): a small, disciplined finance-lexicon addition
   grounded in the Loughran-McDonald Master Dictionary. Candidate terms are
   words that (a) appear often in the headline corpus, (b) are flagged
   Positive/Negative/Uncertainty in the LM dictionary, and (c) are scored
   near-neutral by plain VADER. Each candidate is rated twice independently for
   a VADER-style valence in [-1, +1]; only terms whose two ratings agree in
   sign and magnitude are merged into VADER's lexicon dict (a novel small
   extension, NOT the pre-built finVADER PyPI package).
3. Sector index: average scored headlines to one score per stock per day, carry
   no-news stock-days forward (justified in README), equal-weight stocks within
   each sector, then lag the signal by one equity trading day so day t's signal
   uses only sentiment from day t-1 or earlier.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pandas as pd
from nltk.sentiment import SentimentIntensityAnalyzer

_SRC = Path(__file__).resolve().parent
LM_CSV = _SRC / "lexicons" / "Loughran-McDonald_MasterDictionary_1993-2025.csv"
EXTENSION_CSV = _SRC / "lexicons" / "finvader_lite_extension.csv"

# LM category columns: each holds the YEAR the word joined that category; treat
# any nonzero value as "flagged in that category", never as a number.
LM_CATEGORIES = [
    "Negative", "Positive", "Uncertainty", "Litigious",
    "Strong_Modal", "Weak_Modal", "Constraining",
]

VALENCE_TO_VADER_SCALE = 4.0  # map a [-1, +1] valence rating onto VADER's lexicon scale


# ---------------------------------------------------------------------------
# Loughran-McDonald dictionary
# ---------------------------------------------------------------------------

def load_lm_dictionary() -> pd.DataFrame:
    """Load the LM Master Dictionary, keeping only Word and the category columns."""
    df = pd.read_csv(LM_CSV)
    keep = ["Word", *LM_CATEGORIES]
    df = df[keep].copy()
    df = df.rename(columns={"Word": "word"})
    df["word"] = df["word"].str.lower()
    return df


def lm_flags(lm: pd.DataFrame) -> dict[str, set[str]]:
    """Map lowercase word -> set of categories it is flagged in (nonzero = flagged)."""
    flags = {}
    cat_cols = [c for c in LM_CATEGORIES if c in lm.columns]
    for _, row in lm.iterrows():
        cats = {c for c in cat_cols if row[c] != 0}
        if cats:
            flags[row["word"]] = cats
    return flags


# ---------------------------------------------------------------------------
# finVADER-lite: extension lexicon
# ---------------------------------------------------------------------------

def load_lexicon_extension() -> dict[str, float]:
    """Read the committed extension lexicon; returns {word: vader_lexicon_value}.

    Only rows with status == 'kept' are merged into VADER. 'flagged' rows are
    kept in the file for transparency but excluded (their two ratings disagreed).
    """
    df = pd.read_csv(EXTENSION_CSV)
    kept = df[df["status"] == "kept"]
    return {
        row["word"]: float(row["vader_lexicon_score"])
        for _, row in kept.iterrows()
    }


def build_finvader_lite() -> SentimentIntensityAnalyzer:
    """SentimentIntensityAnalyzer whose lexicon is extended with finVADER-lite."""
    sia = SentimentIntensityAnalyzer()
    sia.lexicon.update(load_lexicon_extension())
    return sia


def build_plain_vader() -> SentimentIntensityAnalyzer:
    """Plain (unmodified) VADER for the before/after comparison."""
    return SentimentIntensityAnalyzer()


# ---------------------------------------------------------------------------
# Reproducible candidate identification (prompt step 2)
# ---------------------------------------------------------------------------

def build_lexicon_candidates(
    headlines: pd.DataFrame,
    min_freq: int = 40,
    max_abs_mean: float = 0.25,
    min_headlines: int = 20,
    top_n: int | None = 80,
) -> pd.DataFrame:
    """Identify candidate finance terms plain VADER is missing.

    Terms that (a) appear >= min_freq times in the corpus, (b) are flagged in the
    LM dictionary, and (c) have |mean plain-VADER compound| < max_abs_mean across
    the headlines containing them (i.e. VADER leaves them near-neutral).

    top_n truncates to the most frequent qualifying terms (screen view). Pass
    top_n=None to get the FULL qualifying pool - the audit ledger in
    scripts/audit_lexicon_traceability.py uses this so no qualifying term is
    silently hidden by the display cutoff.

    This is the data-driven identification step; the two-pass rating that decides
    what is actually kept lives in ai/lexicon_extension_log.md and is encoded in
    src/lexicons/finvader_lite_extension.csv.
    """
    titles = headlines["title"].astype(str)
    sia = build_plain_vader()
    compounds = titles.apply(lambda t: sia.polarity_scores(t)["compound"])

    # token -> row indices (exact-token frequency, ~ word-boundary match)
    word_docs: dict[str, list[int]] = defaultdict(list)
    for i, t in enumerate(titles):
        for tok in set(re.findall(r"[a-zA-Z][a-zA-Z\-]*", t.lower())):
            word_docs[tok].append(i)

    flags = lm_flags(load_lm_dictionary())

    rows = []
    for word, idxs in word_docs.items():
        if len(idxs) < min_freq or word not in flags:
            continue
        comps = compounds.iloc[idxs]
        if len(comps) < min_headlines:
            continue
        mean = float(comps.mean())
        if abs(mean) > max_abs_mean:
            continue
        rows.append({
            "word": word,
            "n_headlines": len(idxs),
            "mean_plain_vader": round(mean, 3),
            "lm_categories": ",".join(sorted(flags[word])),
        })
    df = pd.DataFrame(rows).sort_values("n_headlines", ascending=False)
    if top_n is not None:
        df = df.head(top_n)
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_headlines(
    panel: pd.DataFrame,
    analyzer: SentimentIntensityAnalyzer,
) -> pd.DataFrame:
    """Score every headline's raw text and return the panel with a 'compound' col.

    The panel must have a 'title' column. Returns a new frame with the compound
    score per headline (raw text is scored untouched - no stripping).
    """
    df = panel.copy()
    df["compound"] = df["title"].astype(str).apply(
        lambda t: analyzer.polarity_scores(t)["compound"]
    )
    return df


# ---------------------------------------------------------------------------
# Stock-day sentiment panel and the sector index
# ---------------------------------------------------------------------------

def build_stock_sentiment_panels(
    headline_scores: pd.DataFrame,
    equity_trading_dates: pd.DatetimeIndex,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Average headline scores to one score per stock per trading day.

    Returns (aligned, lagged):
    - aligned: date x ticker frame of mean compound per (ticker, trading day).
      No-news stock-days are carried forward from the last score; leading days
      before a stock's first headline are neutral (0) - no information yet.
    - lagged: aligned shifted one equity trading day, so the value on day t
      uses only sentiment from day t-1 or earlier (look-ahead-safe signal).
    """
    daily = (
        headline_scores.groupby(["ticker", "date"])["compound"]
        .mean()
        .reset_index()
    )
    wide = daily.pivot(index="date", columns="ticker", values="compound")
    wide = wide.reindex(index=pd.DatetimeIndex(equity_trading_dates).sort_values(),
                        columns=sorted(wide.columns))
    aligned_filled = wide.ffill().fillna(0.0)  # carry-forward; leading -> neutral
    lagged = aligned_filled.shift(1)
    return aligned_filled, lagged


def build_sector_sentiment_index(
    headline_scores: pd.DataFrame,
    equity_trading_dates: pd.DatetimeIndex,
    sector_map: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build the daily sector sentiment index (equal-weight stocks in a sector).

    Returns (index_long, aligned, lagged):
    - index_long: long frame with date, sector, sentiment (LAGGED - the trading
      signal) and sentiment_aligned (the raw aligned index, for display).
    - aligned / lagged: the stock-level panels (lagged is the fusion input).

    No-news stock-days: carried forward (see README for the justification).
    The saved 'sentiment' column is already lagged one trading day.
    """
    aligned, lagged = build_stock_sentiment_panels(headline_scores, equity_trading_dates)

    sectors = sorted({s for s in sector_map.values()})
    rows = []
    for sector in sectors:
        tickers = [t for t, s in sector_map.items() if s == sector]
        tickers = [t for t in tickers if t in aligned.columns]
        if not tickers:
            continue
        idx = lagged[tickers].mean(axis=1)
        idx_aligned = aligned[tickers].mean(axis=1)
        n = len(tickers)
        for d in idx.index:
            rows.append({
                "date": d,
                "sector": sector,
                "sentiment": float(idx[d]) if not pd.isna(idx[d]) else 0.0,
                "sentiment_aligned": float(idx_aligned[d]) if not pd.isna(idx_aligned[d]) else 0.0,
                "n_stocks": n,
            })
    index_long = pd.DataFrame(rows)
    return index_long, aligned, lagged
