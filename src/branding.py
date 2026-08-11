"""Investor-facing display names for every fund id (Prompt 03).

Fund ids stay technical everywhere data is stored, parsed, and traced
(``parse_fund_id``, the ``fund`` columns in the results CSVs, the prompt
logs, and every test). These dicts are a presentation-only layer: they map
technical ids to the names a person actually reads (figure text, the report,
the Station 4 app). See ai/prompt_log.md Entry 8.
"""
from __future__ import annotations

import pandas as pd

# The base fund the sentiment-fusion variants are built on (see src/fusion.py).
FUSION_BASE_FUND = "equity_min_variance"

DISPLAY_NAMES = {
    # Core 12
    "equity_equal_weight": "Invesper US Equity Index Fund",
    "equity_min_variance": "Invesper US Equity Minimum Volatility Fund",
    "equity_max_sharpe": "Invesper US Equity Opportunities Fund",
    "equity_risk_parity": "Invesper US Equity Balanced Risk Fund",
    "crypto_equal_weight": "Invesper Digital Assets Index Fund",
    "crypto_min_variance": "Invesper Digital Assets Minimum Volatility Fund",
    "crypto_max_sharpe": "Invesper Digital Assets Opportunities Fund",
    "crypto_risk_parity": "Invesper Digital Assets Balanced Risk Fund",
    "combined_equal_weight": "Invesper Multi-Asset Index Fund",
    "combined_min_variance": "Invesper Multi-Asset Minimum Volatility Fund",
    "combined_max_sharpe": "Invesper Multi-Asset Opportunities Fund",
    "combined_risk_parity": "Invesper Multi-Asset Balanced Risk Fund",
    # 5 groupings (10 funds)
    "defensive_equal_weight": "Invesper Defensive Sectors Index Fund",
    "defensive_risk_parity": "Invesper Defensive Sectors Balanced Risk Fund",
    "cyclical_equal_weight": "Invesper Cyclical Sectors Index Fund",
    "cyclical_risk_parity": "Invesper Cyclical Sectors Balanced Risk Fund",
    "growth_sensitive_equal_weight": "Invesper Growth & Innovation Sectors Index Fund",
    "growth_sensitive_risk_parity": "Invesper Growth & Innovation Sectors Balanced Risk Fund",
    "payments_equal_weight": "Invesper Digital Payments Index Fund",
    "payments_risk_parity": "Invesper Digital Payments Balanced Risk Fund",
    "web3infra_equal_weight": "Invesper Web3 Infrastructure Index Fund",
    "web3infra_risk_parity": "Invesper Web3 Infrastructure Balanced Risk Fund",
}

FUSION_DISPLAY_NAMES = {
    "momentum": "Invesper US Equity Minimum Volatility Fund (Momentum)",
    "contrarian": "Invesper US Equity Minimum Volatility Fund (Contrarian)",
}

VOL_TARGET_DISPLAY_NAMES = {
    "combined_max_sharpe": "Invesper Multi-Asset Opportunities Fund (Managed Vol)",
    "crypto_max_sharpe": "Invesper Digital Assets Opportunities Fund (Managed Vol)",
}

# Fixed tiered annual management fee (decimal) per fund id (prompt_06 item 6).
# Not user-editable: real platforms price each fund by its own strategy. Loosely
# Vanguard-style - passive index funds cheapest, actively-managed/thematic
# pricier, crypto priced at a premium over the equivalent equity strategy, and
# the fusion/vol-target variants priciest as the most "actively managed".
# The app reads this via results/data/fund_fees.csv (never a src.* import).
FEE_SCHEDULE = {
    # Core equity
    "equity_equal_weight": 0.0005,      # 0.05%
    "equity_min_variance": 0.0020,      # 0.20%
    "equity_max_sharpe": 0.0045,        # 0.45%
    "equity_risk_parity": 0.0030,       # 0.30%
    # Core crypto (premium over equivalent equity strategies)
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
    # Extension variants (most actively managed - priced highest)
    "equity_min_variance_momentum": 0.0085,
    "equity_min_variance_contrarian": 0.0085,
    "combined_max_sharpe_vol_targeted": 0.0075,
    "crypto_max_sharpe_vol_targeted": 0.0095,
}

# Row identifiers the comparison CSVs use for variant rows
# (src/fusion.py writes {base}_base and {base}_{variant}; src/vol_target.py
# writes {label}_base and {label}_vol_targeted).
_VOL_TARGET_SUFFIX = "_vol_targeted"
_BASE_SUFFIX = "_base"


def fund_display_name(fund_id: str) -> str:
    """Display name for a fund id, including fusion/vol-target CSV variants."""
    if fund_id in DISPLAY_NAMES:
        return DISPLAY_NAMES[fund_id]
    if fund_id.endswith(_VOL_TARGET_SUFFIX):
        label = fund_id[: -len(_VOL_TARGET_SUFFIX)]
        if label in VOL_TARGET_DISPLAY_NAMES:
            return VOL_TARGET_DISPLAY_NAMES[label]
    elif fund_id.endswith(_BASE_SUFFIX):
        base = fund_id[: -len(_BASE_SUFFIX)]
        if base in DISPLAY_NAMES:
            return DISPLAY_NAMES[base]
    else:
        for variant, name in FUSION_DISPLAY_NAMES.items():
            suffix = f"_{variant}"
            if fund_id.endswith(suffix) and fund_id[: -len(suffix)] == FUSION_BASE_FUND:
                return name
    raise KeyError(f"no display name for fund id {fund_id!r}")


def display_names_table() -> pd.DataFrame:
    """Every fund id in the codebase mapped to its display name (for the CSV).

    Covers the 22 base funds plus every fusion/vol-target variant row that
    appears in the comparison CSVs, so Station 4 can look up any fund id.
    """
    ids = list(DISPLAY_NAMES)
    ids += [f"{FUSION_BASE_FUND}{_BASE_SUFFIX}"]
    ids += [f"{FUSION_BASE_FUND}_{variant}" for variant in FUSION_DISPLAY_NAMES]
    for label in VOL_TARGET_DISPLAY_NAMES:
        ids += [f"{label}{_BASE_SUFFIX}", f"{label}{_VOL_TARGET_SUFFIX}"]
    return pd.DataFrame({
        "fund_id": ids,
        "display_name": [fund_display_name(f) for f in ids],
    })


def fees_table() -> pd.DataFrame:
    """The fixed per-fund management fee schedule (for the app's CSV)."""
    return pd.DataFrame({
        "fund_id": list(FEE_SCHEDULE),
        "fee_annual": [FEE_SCHEDULE[f] for f in FEE_SCHEDULE],
    })


def family_display_prefix(family: str) -> str:
    """Shared leading words of a family's fund names (e.g. 'Invesper US Equity')."""
    names = [name for fund_id, name in DISPLAY_NAMES.items()
             if fund_id.startswith(f"{family}_")]
    if not names:
        raise KeyError(f"no display names for family {family!r}")
    prefix = names[0]
    for name in names[1:]:
        common = []
        for a, b in zip(prefix, name):
            if a != b:
                break
            common.append(a)
        prefix = "".join(common)
    return prefix.strip()


def wrap_display_name(name: str, width: int = 24) -> str:
    """Wrap a display name at word boundaries (for table/axis labels)."""
    lines, cur = [], ""
    for word in name.split():
        if cur and len(cur) + 1 + len(word) <= width:
            cur = f"{cur} {word}"
        elif cur:
            lines.append(cur)
            cur = word
        else:
            cur = word
    if cur:
        lines.append(cur)
    return "\n".join(lines)
