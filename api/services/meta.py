# -*- coding: utf-8 -*-
"""Static reference data for the front end (descriptions, presets, profiles)."""

from __future__ import annotations

from utils.constants import SECTOR_ETF
from utils.metrics import FUNDAMENTAL_DESC, METRIC_DESC, TECHNICAL_DESC
from utils.prescription import INVESTOR_PROFILES, PROFILE_DESCRIPTIONS
from utils.screener_filters import FILTER_PRESETS

HORIZONS = [
    {"label": "3 Months", "value": "3mo"}, {"label": "6 Months", "value": "6mo"},
    {"label": "1 Year", "value": "1y"}, {"label": "2 Years", "value": "2y"},
    {"label": "5 Years", "value": "5y"}, {"label": "10 Years", "value": "10y"},
]

NOTES = {
    "alpha_rf": (
        "Portfolio alpha converts the annual risk-free rate with (1+rf)^(1/252)-1, "
        "whereas Sharpe/Sortino use rf/252. Both are kept to match the original app."
    ),
}


def build_meta() -> dict:
    return {
        "metric_desc": METRIC_DESC,
        "fundamental_desc": FUNDAMENTAL_DESC,
        "technical_desc": TECHNICAL_DESC,
        "profiles": {k: {"weights": v, "description": PROFILE_DESCRIPTIONS.get(k, "")}
                     for k, v in INVESTOR_PROFILES.items()},
        "sector_etf": SECTOR_ETF,
        "horizons": HORIZONS,
        "filter_presets": {
            key: [{"label": lbl, "min": lo, "max": hi} for (lbl, lo, hi) in opts]
            for key, opts in FILTER_PRESETS.items()
        },
        "notes": NOTES,
    }
